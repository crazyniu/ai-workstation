#!/usr/bin/env python3
"""Opt-in fixed workstation egress and per-client DNS; run inside the gateway."""
import argparse
import copy
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import secrets
import socket
import struct
import subprocess
import tempfile
import urllib.parse
import urllib.request

import yaml
import state

PRIVATE_RULES = [
    'DOMAIN,localhost,DIRECT', 'DOMAIN-SUFFIX,local,DIRECT', 'DOMAIN-SUFFIX,lan,DIRECT',
    *[f'IP-CIDR,{net},DIRECT,no-resolve' for net in
      ('127.0.0.0/8', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16',
       '169.254.0.0/16', '100.64.0.0/10', '224.0.0.0/4')],
    *[f'IP-CIDR6,{net},DIRECT,no-resolve' for net in ('::1/128', 'fc00::/7', 'fe80::/10')],
]


def source_address(value):
    ip = ipaddress.IPv4Address(value)
    if ip.is_unspecified or ip.is_multicast or ip.is_loopback:
        raise ValueError('Use the workstation LAN IPv4 address')
    return str(ip)


def endpoint_proxy(config, name):
    node = next((p for p in config.get('proxies', []) if p.get('name') == name), None)
    if not node or node.get('type', '').lower() in ('direct', 'reject', 'pass'):
        raise ValueError('Select an existing concrete proxy endpoint, not a group or DIRECT')
    if ',' in name or '\n' in name or '\r' in name:
        raise ValueError('The proxy name cannot contain rule delimiters')


def require_gateway(config):
    if config.get('mode', 'rule').lower() != 'rule' or not config.get('tun', {}).get('enable'):
        raise ValueError('An enabled transparent TUN gateway in rule mode is required')


def pinned_config(config, source, proxy):
    source = source_address(source)
    endpoint_proxy(config, proxy)
    require_gateway(config)
    result = copy.deepcopy(config)
    key = 'WORKSTATION-EXIT-' + source.replace('.', '-')
    exact = f'SRC-IP-CIDR,{source}/32,'
    sub = f'SUB-RULE,(SRC-IP-CIDR,{source}/32),'
    # Replace this source's old dispatch only; other clients retain rule ordering.
    other = [r for r in result.get('rules', []) if not str(r).startswith((exact, sub))]
    result.setdefault('sub-rules', {})[key] = PRIVATE_RULES + [f'MATCH,{proxy}']
    result['rules'] = [sub + key, exact + 'REJECT', *other]
    return result


def validate_pinned(config, source, proxy):
    source = source_address(source)
    endpoint_proxy(config, proxy)
    require_gateway(config)
    prefix = f'SUB-RULE,(SRC-IP-CIDR,{source}/32),'
    rules = config.get('rules', [])
    for i, rule in enumerate(rules):
        if str(rule).startswith(prefix):
            key = rule[len(prefix):]
            body = config.get('sub-rules', {}).get(key, [])
            if not body or body[-1] != f'MATCH,{proxy}' or any(r not in PRIVATE_RULES for r in body[:-1]):
                break
            if i + 1 >= len(rules) or rules[i + 1] != f'SRC-IP-CIDR,{source}/32,REJECT':
                break
            return
        # Earlier source-specific rules for another exact IPv4 address cannot
        # intercept this workstation. Unknown predicates are rejected safely.
        addresses = re.findall(r'SRC-IP-CIDR,([0-9.]+)/32', str(rule))
        if not addresses or source in addresses or not str(rule).startswith('AND,((SRC-IP-CIDR,'):
            break
    raise ValueError('Install the fixed source route first; no DNS configuration was changed')


def private_override(upstream):
    match = re.fullmatch(r'\[/(.+)/\](.+)', upstream)
    if not match:
        return False
    domains = [d.lower().rstrip('.') for d in match[1].split('/')]
    if not all(d in ('home.arpa', 'lan', 'local') or d.endswith('.ts.net') for d in domains):
        return False
    url = urllib.parse.urlsplit(match[2] if '://' in match[2] else '//' + match[2])
    try:
        ip = ipaddress.ip_address(url.hostname)
    except ValueError:
        return False
    return ip.is_private or ip in ipaddress.ip_network('100.64.0.0/10')


def dns_client(previous, source, port):
    source = source_address(source)
    if not 1024 <= port <= 65535:
        raise ValueError('Use an unprivileged resolver port')
    if previous and previous.get('ids') != [source]:
        raise ValueError('Split shared client identifiers before changing this workstation')
    client = copy.deepcopy(previous) if previous else {
        'name': 'Workstation ' + source, 'ids': [source], 'use_global_settings': True,
        'use_global_blocked_services': True, 'filtering_enabled': True,
    }
    client['upstreams'] = [f'tcp://{source}:{port}'] + [
        u for u in client.get('upstreams', []) if private_override(u)]
    return client


def request(path, data=None, method=None, controller=False):
    headers = {'Content-Type': 'application/json'}
    if controller:
        headers['Authorization'] = 'Bearer ' + str(state.config().get('secret', ''))
    base = 'http://127.0.0.1:9090' if controller else 'http://127.0.0.1:3000/control'
    req = urllib.request.Request(base + path, data=None if data is None else json.dumps(data).encode(),
                                 headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=15) as response:
        body = response.read()
    return json.loads(body) if body else {}


def clients_for(source):
    matches = [c for c in request('/clients')['clients'] if source in c.get('ids', [])]
    if len(matches) > 1 or any(c.get('ids') != [source] for c in matches):
        raise ValueError('This source belongs to a shared or ambiguous client record')
    return matches[0] if matches else None


def update_client(before, after):
    if before and after:
        request('/clients/update', {'name': before['name'], 'data': after})
    elif after:
        request('/clients/add', after)
    elif before:
        request('/clients/delete', {'name': before['name']})


def backup(action, source, before):
    folder = state.ROOT / 'backups' / ('workstation-egress-' + secrets.token_hex(8))
    folder.mkdir(mode=0o700)
    state.save(folder / 'record.json', {'action': action, 'source': source, 'before': before})
    return folder


def validate_mihomo(body):
    with tempfile.NamedTemporaryFile(dir=state.CONFIG.parent, suffix='.yaml') as candidate:
        candidate.write(body)
        candidate.flush()
        subprocess.run([str(state.ROOT / 'components/current/mihomo/mihomo'), '-t',
                        '-d', str(state.CONFIG.parent), '-f', candidate.name],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def reload_mihomo():
    request('/configs?force=true', {'path': str(state.CONFIG)}, method='PUT', controller=True)


def probe_resolver(source, port):
    ident = secrets.randbelow(65536)
    query = struct.pack('!HHHHHH', ident, 0x100, 1, 0, 0, 0) + b'\x07example\x03com\0' + struct.pack('!HH', 1, 1)
    with socket.create_connection((source, port), timeout=8) as stream:
        stream.settimeout(8)
        stream.sendall(struct.pack('!H', len(query)) + query)
        def receive(size):
            result = b''
            while len(result) < size:
                part = stream.recv(size - len(result))
                if not part:
                    raise ValueError('Resolver closed an incomplete DNS response')
                result += part
            return result
        reply = receive(struct.unpack('!H', receive(2))[0])
    header = struct.unpack('!HHHHHH', reply[:12])
    if header[0] != ident or header[1] & 15 or not header[3]:
        raise ValueError('The dedicated resolver did not resolve the test domain')


def configure(action, source, proxy, port, apply=False):
    initial = state.CONFIG.read_bytes()
    config = yaml.safe_load(initial)
    if action == 'route':
        candidate = pinned_config(config, source, proxy)
        if not apply:
            return {'action': action, 'source': source, 'proxy': proxy, 'apply': False}
        require_gateway(request('/configs', controller=True))
        body = yaml.safe_dump(candidate, allow_unicode=True, sort_keys=False).encode()
        validate_mihomo(body)
        before = initial
        if state.CONFIG.read_bytes() != initial:
            raise ValueError('Proxy configuration changed during validation; retry from a fresh plan')
        folder = backup(action, source, None)
        state.atomic(folder / 'mihomo.yaml', before)
        try:
            state.atomic(state.CONFIG, body)
            reload_mihomo()
        except Exception:
            state.atomic(state.CONFIG, before)
            reload_mihomo()
            raise
        record = state.read(folder / 'record.json')
        record['after_sha256'] = hashlib.sha256(body).hexdigest()
    else:
        validate_pinned(config, source, proxy)
        before = clients_for(source)
        after = dns_client(before, source, port)
        if not apply:
            return {'action': action, 'source': source, 'upstream': after['upstreams'][0], 'apply': False}
        require_gateway(request('/configs', controller=True))
        probe_resolver(source, port)
        if state.CONFIG.read_bytes() != initial or clients_for(source) != before:
            raise ValueError('Proxy or client settings changed during validation; retry')
        folder = backup(action, source, before)
        try:
            update_client(before, after)
            current = clients_for(source)
            if current.get('upstreams') != after['upstreams']:
                raise ValueError('Client update verification failed')
        except Exception:
            update_client(clients_for(source), before)
            raise
        record = state.read(folder / 'record.json')
        record['after'] = current
    state.save(folder / 'record.json', record)
    return {'action': action, 'source': source, 'backup': str(folder), 'apply': True}


def rollback(folder, apply=False):
    root = (state.ROOT / 'backups').resolve()
    folder = Path(folder).resolve()
    if folder.parent != root or not folder.name.startswith('workstation-egress-'):
        raise ValueError('Use a backup directory created by this command')
    record = state.read(folder / 'record.json')
    if not record:
        raise ValueError('Backup record not found')
    if record['action'] == 'route':
        current = state.CONFIG.read_bytes()
        if hashlib.sha256(current).hexdigest() != record.get('after_sha256'):
            raise ValueError('Proxy configuration changed since apply; automatic rollback refused')
        old = (folder / 'mihomo.yaml').read_bytes()
        validate_mihomo(old)
        if apply:
            if state.CONFIG.read_bytes() != current:
                raise ValueError('Proxy configuration changed during rollback validation')
            try:
                state.atomic(state.CONFIG, old)
                reload_mihomo()
            except Exception:
                state.atomic(state.CONFIG, current)
                reload_mihomo()
                raise
    else:
        current = clients_for(record['source'])
        if current != record.get('after'):
            raise ValueError('Client settings changed since apply; automatic rollback refused')
        if apply:
            update_client(current, record['before'])
    return {'rollback': str(folder), 'apply': apply}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('route', 'dns', 'rollback'))
    parser.add_argument('--source-ip')
    parser.add_argument('--exit-proxy')
    parser.add_argument('--port', type=int, default=5354)
    parser.add_argument('--backup')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.action == 'rollback':
        if not args.backup:
            parser.error('--backup is required for rollback')
        result = rollback(args.backup, args.apply)
    else:
        if not args.source_ip or not args.exit_proxy:
            parser.error('--source-ip and --exit-proxy are required')
        result = configure(args.action, source_address(args.source_ip), args.exit_proxy, args.port, args.apply)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
