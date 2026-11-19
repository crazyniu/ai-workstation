"""Compile the administrator's Clash rules into a private, enforced runtime config."""
import copy
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys

import yaml

import state
from routing_groups import apply_switches, merge_subscription_nodes, policy_slot

RUNTIME_NAME = '.gateway-effective.yaml'
DIRECT_MARK = 6667
PRIVATE4 = ('0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8', '169.254.0.0/16',
            '172.16.0.0/12', '192.168.0.0/16', '224.0.0.0/4', '240.0.0.0/4')


def isolated_clients():
    return [str(ipaddress.IPv4Address(v)) for v in os.getenv('GATEWAY_ISOLATED_CLIENTS', '').split()]


def local_networks():
    return list(dict.fromkeys([*PRIVATE4, str(ipaddress.ip_interface(os.environ['GATEWAY_LAN_ADDRESS']).network)]))


def protect_dns(adguard, domain):
    begin, end = '! managed workstation DNS begin', '! managed workstation DNS end'
    rules = adguard.get('user_rules') or []
    if begin in rules and end in rules:
        rules = rules[:rules.index(begin)] + rules[rules.index(end) + 1:]
    clients = isolated_clients()
    if clients:
        zones = {domain, 'home.arpa', 'lan', 'local', 'ip6.arpa'}
        for block in local_networks():
            network = ipaddress.ip_network(block)
            # Reverse DNS zones are delegated on octet boundaries.
            for part in network.subnets(new_prefix=(network.prefixlen + 7) // 8 * 8):
                octets = str(part.network_address).split('.')[:part.prefixlen // 8]
                zones.add('.'.join([*reversed(octets), 'in-addr', 'arpa']))
        rules += [begin, *[f"||{zone}^$important,client={'|'.join(clients)}" for zone in sorted(zones)], end]
    if clients or 'user_rules' in adguard:
        adguard['user_rules'] = rules


def install_firewall():
    clients = isolated_clients()
    if not clients:
        return
    sources = ', '.join(clients)
    local = '\n'.join(f'meta mark {DIRECT_MARK} ip daddr {net} reject' for net in local_networks())
    tun = (state.config().get('tun') or {}).get('device', 'Mihomo') if state.CONFIG.exists() else 'Mihomo'
    lan = ipaddress.ip_interface(os.environ['GATEWAY_LAN_ADDRESS']).network
    iface = json.dumps(os.environ['GATEWAY_RUNTIME_INTERFACE'])
    # The restricted DIRECT adapter applies its mark to the socket, so the
    # final address is checked even if a hostname has several addresses.
    rules = f"""
add table inet workstation_boundary
delete table inet workstation_boundary
table inet workstation_boundary {{
  chain output {{
    type filter hook output priority -10; policy accept;
    {local}
    meta mark {DIRECT_MARK} fib daddr type {{ local, broadcast, multicast }} reject
    meta mark {DIRECT_MARK} meta nfproto ipv6 reject
  }}
  chain input {{
    type filter hook input priority -10; policy accept;
    ip saddr {{ {sources} }} ct direction reply ct state {{ established, related }} accept
    ip saddr {{ {sources} }} tcp dport {{ 53, 5353, 7890, 7891 }} accept
    ip saddr {{ {sources} }} udp dport {{ 53, 5353 }} accept
    ip saddr {{ {sources} }} reject
  }}
  chain forward {{
    type filter hook forward priority -10; policy accept;
    ip saddr {{ {sources} }} ct direction reply ct state {{ established, related }} accept
    ip saddr {{ {sources} }} oifname != {json.dumps(tun)} reject
    iifname {iface} oifname {iface} ip daddr != {lan} ct direction original reject
  }}
}}
"""
    subprocess.run(['nft', '-f', '-'], input=rules, text=True, check=True)


def parent_groups(groups, names):
    result = set(names)
    while True:
        parents = {name for name, group in groups.items()
                   if result.intersection(group.get('proxies') or [])}
        if parents <= result:
            return result
        result.update(parents)


def effective(source):
    config = copy.deepcopy(source)
    merge_subscription_nodes(config)
    for group in config.get('proxy-groups', []):
        group.pop('x-gateway-empty-subscription', None)
        if len(group.get('use') or []) > 1 and not group.get('filter'):
            # Mihomo's ordered-filter pass unions providers by node name. The
            # first tier matches every name and preserves provider order.
            group['filter'] = '.*`^$'
    apply_switches(config)
    clients = isolated_clients()
    nodes = {p['name']: p for p in config.get('proxies') or []}
    groups = {g['name']: g for g in config.get('proxy-groups') or []}
    fixed = {name for name, p in nodes.items() if p.get('type') in ('http', 'socks5')}
    if fixed:
        fixed.update(name for name, g in groups.items() if g.get('include-all-proxies') or g.get('include-all'))
    fixed = parent_groups(groups, fixed)
    pools = {name for name, g in groups.items() if g.get('use') or g.get('include-all-providers') or g.get('include-all')}
    guarded = parent_groups(groups, fixed | pools)
    for name, group in groups.items():
        if name in guarded:
            group['empty-fallback'] = 'REJECT'
        if name in fixed:
            # Automatic reselection would silently replace a designated exit.
            if group['type'] in ('url-test', 'fallback', 'load-balance'):
                group['type'] = 'select'
    if not clients and not guarded:
        return config
    if str(config.get('mode', 'rule')).lower() != 'rule':
        if clients or fixed:
            raise ValueError('启用工作站隔离或固定 HTTP 出口时，Clash 必须使用 rule 模式')
        return config

    base = list(config.get('rules') or [])
    sub = config.get('sub-rules') or {}
    generated = {}
    used = set(nodes) | set(groups) | set(sub)

    def new_name(stem):
        name = stem
        while name in used:
            name += '_'
        used.add(name)
        return name

    def rewrite(rule, target_map, sub_map):
        fields, i = policy_slot(rule)
        if not i:
            return rule
        name = fields[i].strip()
        fields[i] = sub_map.get(name, name) if fields[0].strip().upper() == 'SUB-RULE' else target_map(name)
        return ','.join(fields)

    def clone_tables(prefix, target_map):
        names = {name: new_name(prefix + str(i)) for i, name in enumerate(sub)}
        for name, rules in sub.items():
            generated[names[name]] = [rewrite(rule, target_map, names) for rule in rules]
        return names

    rules = []
    if clients:
        direct = new_name('Gateway-Workstation-Direct')
        config['proxies'] = list(config.get('proxies') or [])
        config['proxies'].append({'name': direct, 'type': 'direct', 'routing-mark': DIRECT_MARK,
                                  'ip-version': 'ipv4'})
        # A shared group containing unrestricted DIRECT cannot inherit a
        # per-client socket mark. Reject that ambiguous route for 251 only.
        local_adapters = {'DIRECT', 'COMPATIBLE', 'GLOBAL', 'DNS', 'PASS', 'PASS-RULE'}
        local_adapters.update(n for n, p in nodes.items() if p.get('type') in ('direct', 'dns', 'pass', 'rematch'))
        unsafe = parent_groups(groups, local_adapters | {n for n, g in groups.items()
                               if g.get('empty-fallback') in local_adapters or g.get('include-all') or g.get('include-all-proxies')})
        def restricted(name):
            if name in ('DIRECT', 'COMPATIBLE') or nodes.get(name, {}).get('type') == 'direct':
                return direct
            return 'REJECT' if name in unsafe else name

        # Empty provider sets must never expand into the built-in DIRECT adapter.
        for name, group in groups.items():
            if name not in unsafe:
                group.setdefault('empty-fallback', 'REJECT')
            if name not in unsafe and name in pools:
                excluded = (group.get('exclude-type') or '').split('|')
                group['exclude-type'] = '|'.join(dict.fromkeys(t for t in
                    [*excluded, 'Direct', 'Compatible', 'Pass', 'PassRule', 'Dns', 'Rematch'] if t))
            if group.get('include-all') or group.get('include-all-proxies'):
                previous = group.get('exclude-filter')
                group['exclude-filter'] = '|'.join(filter(None, [previous, '^' + direct + '$']))
        client_sub = clone_tables('Gateway-Client-Sub-', restricted)
        scope = new_name('Gateway-Workstation')
        generated[scope] = [
            'DOMAIN,localhost,REJECT', 'DOMAIN-SUFFIX,local,REJECT', 'DOMAIN-SUFFIX,lan,REJECT',
            'DOMAIN-SUFFIX,home.arpa,REJECT', 'DOMAIN-SUFFIX,localhost,REJECT',
            *[f'IP-CIDR,{net},REJECT' for net in local_networks()], 'IP-CIDR6,::/0,REJECT',
            *[rewrite(rule, restricted, client_sub) for rule in base], f'MATCH,{direct}']
        for client in clients:
            rules.extend([f'SUB-RULE,(SRC-IP-CIDR,{client}/32),{scope}', f'SRC-IP-CIDR,{client}/32,REJECT'])

    # A skipped UDP adapter is handled by the outer rule loop, even if its
    # match originated in a nested sub-rule. Mirror that decision at the root.
    def guard_target(name):
        return 'REJECT' if name in guarded else ('PASS-RULE' if name == 'PASS-RULE' else 'PASS')

    shadow = clone_tables('Gateway-Exit-Guard-', guard_target) if guarded else {}
    for rule in base:
        rules.append(rule)
        fields, i = policy_slot(rule)
        if guarded and i and (fields[i].strip() in guarded or fields[0].strip().upper() == 'SUB-RULE'):
            rules.append(rewrite(rule, guard_target, shadow))
    config['rules'] = rules
    if generated:
        config['sub-rules'] = {**sub, **generated}
    return config


def render(source, destination):
    value = yaml.safe_load(Path(source).read_text())
    state.atomic(destination, yaml.safe_dump(effective(value), allow_unicode=True, sort_keys=False))
    return destination


def runtime(source):
    return render(source, Path(source).with_name(RUNTIME_NAME))


if __name__ == '__main__':
    if sys.argv[1] == 'firewall':
        install_firewall()
    else:
        runtime(state.CONFIG)
