"""Edit a Clash YAML draft. Applying it is the existing revision-checked importer’s job."""
import hashlib
import ipaddress
import re
from copy import deepcopy
import json
from urllib.parse import quote, urlsplit

import yaml
import legacy
import state
import routing_groups as routing
import group_domains

from workstation_dns import PRIVATE_RULES

EDITABLE_TYPES = ('http', 'socks5')
BUILTINS = {'DIRECT', 'REJECT', 'REJECT-DROP', 'PASS', 'COMPATIBLE', 'GLOBAL'}
DIRECT_SOURCE = re.compile(r'SRC-IP-CIDR,\s*([^,]+),\s*([^,]+)(?:,\s*no-resolve)?', re.I)
SUB_SOURCE = re.compile(r'SUB-RULE,\s*\(SRC-IP-CIDR,\s*([^,)]+)\),\s*([^,]+)', re.I)


def address_range(value):
    value = value.strip()
    try:
        if '-' in value:
            start, end = (part.strip() for part in value.split('-', 1))
            first = ipaddress.ip_address(start)
            # Allow 192.168.1.240-249 in addition to two complete addresses.
            if first.version == 4 and end.isdecimal():
                end = start.rsplit('.', 1)[0] + '.' + end
            last = ipaddress.ip_address(end)
            if first.version != last.version or first > last:
                raise ValueError
        else:
            network = ipaddress.ip_network(value, strict=False)
            first, last = network.network_address, network.broadcast_address
    except ValueError:
        raise ValueError('请输入有效的单个 IP、CIDR 或起止地址范围') from None
    return first, last


def range_label(first, last):
    return str(first) if first == last else f'{first}-{last}'


def binding_blocks(config):
    rules, subs = config.get('rules') or [], config.get('sub-rules') or {}
    i = 0
    while i < len(rules):
        text = rules[i]
        sub = SUB_SOURCE.fullmatch(text) if isinstance(text, str) else None
        match = sub or (DIRECT_SOURCE.fullmatch(text) if isinstance(text, str) else None)
        if not match:
            i += 1
            continue
        try:
            net = ipaddress.ip_network(match[1].strip(), strict=False)
        except ValueError:
            i += 1
            continue
        target = match[2].strip()
        key = target if sub else None
        end = i + 1
        reject = False
        if sub:
            body = subs.get(key, [])
            target = body[-1][6:].strip() if body and isinstance(body[-1], str) and body[-1].startswith('MATCH,') else None
            fallback = DIRECT_SOURCE.fullmatch(rules[end]) if end < len(rules) and isinstance(rules[end], str) else None
            reject = bool(fallback and fallback[1].strip() == match[1].strip() and fallback[2].strip() == 'REJECT')
            end += int(reject)
        if target and target not in ('REJECT', 'DIRECT', 'REJECT-DROP'):
            yield dict(id=i, first=net.network_address, last=net.broadcast_address, target=target,
                       sub=key, end=end, reject=reject)
        i = end


def bindings(config):
    # One range may occupy several consecutive CIDR dispatch/guard pairs.
    pending = None
    for row in binding_blocks(config):
        if (pending and row['sub'] and row['sub'] == pending['sub'] and row['reject'] == pending['reject']
                and pending['end'] == row['id'] and pending['first'].version == row['first'].version
                and int(pending['last']) + 1 == int(row['first'])):
            pending.update(last=row['last'], end=row['end'])
        else:
            if pending:
                yield dict(pending, ip=range_label(pending['first'], pending['last']))
            pending = row
    if pending:
        yield dict(pending, ip=range_label(pending['first'], pending['last']))


def policy_names(config):
    return [entry['name'] for section in ('proxies', 'proxy-groups') for entry in (config.get(section) or [])
            if isinstance(entry, dict) and isinstance(entry.get('name'), str)]


def live_pool(config):
    names = {g.get('name') for g in config.get('proxy-groups', [])}
    name = next((n for n in (routing.PROXY, 'Proxy', 'PROXY', '🤖 AI', 'AI') if n in names), None)
    if not name:
        return {}
    try:
        info = json.loads(legacy.controller_request('/proxies/' + quote(name, safe='')))
        return {'all': [routing.ALIASES.get(n, n) if n in names else n for n in info.get('all', [])],
                'now': routing.ALIASES.get(info['now'], info['now']) if info.get('now') in names else info.get('now', '')}
    except (OSError, ValueError):
        return {}


def model(config):
    for section, shape in (('rules', list), ('sub-rules', dict), ('proxies', list),
                           ('proxy-groups', list), ('rule-providers', dict), ('proxy-providers', dict)):
        if config.get(section) is not None and not isinstance(config[section], shape):
            raise ValueError(f'{section} 需要使用' + ('列表' if shape is list else '字段组'))
    lists = [config.get('rules') or [], *(config.get('sub-rules') or {}).values()]
    for provider in (config.get('rule-providers') or {}).values():
        if not isinstance(provider, dict):
            raise ValueError('每个规则集需要使用字段组')
        if 'payload' in provider:
            lists.append(provider['payload'])
    if any(not isinstance(items, list) or not all(isinstance(item, str) for item in items) for items in lists):
        raise ValueError('规则和规则集条目需要使用文本列表')
    nodes = [n for n in config.get('proxies') or [] if isinstance(n, dict) and n.get('name')]
    groups = [g for g in config.get('proxy-groups') or [] if isinstance(g, dict) and g.get('name')]
    own_host = state.settings()['domain']
    fixed = {key: True for key in legacy.GATEWAY_KEYS}
    fixed.update({k: list(fields) for k, fields in legacy.NETWORK_OWNED.items()}, hosts=[own_host])
    options = {}
    for key, value in config.items():
        locked = fixed.get(key)
        if locked is not True and key not in (routing.NOTES, routing.DISABLED):
            options[key] = ({k: v for k, v in value.items() if k not in locked}
                            if locked and isinstance(value, dict) else value)
    return {
        'providers': [{'name': name, 'url': entry.get('url', '')}
                      for name, entry in (config.get('proxy-providers') or {}).items()
                      if isinstance(entry, dict) and entry.get('type') == 'http'],
        'exits': [{key: node[key] for key in ('name', 'type', 'server', 'port', 'username', 'password',
                                              'dialer-proxy', 'tls') if key in node}
                  for node in nodes if node.get('type') in EDITABLE_TYPES],
        'bindings': [dict(id=r['id'], end=r['end'], sub=r['sub'], ip=r['ip'], target=r['target'], note=(config.get(routing.NOTES) or {}).get(r['ip'], ''))
                     for r in bindings(config)],
        'deviceExits': routing.exits(config), 'defaultPolicy': routing.default_policy(config),
        'disabledGroups': config.get(routing.DISABLED, []),
        'targets': policy_names(config),
        'groups': [{'name': group['name'], 'members': group.get('proxies') or []} for group in groups],
        'options': options, 'fixed': fixed,
    }


def edit_provider(config, edit):
    name = edit['name'].strip()
    providers = config.setdefault('proxy-providers', {})
    if edit.get('remove'):
        if name not in providers:
            raise ValueError('请选择已有节点订阅')
        del providers[name]
        routing.merge_subscription_nodes(config, removed=(name,))
        return
    url = edit['url'].strip()
    parsed = urlsplit(url)
    if not name or parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise ValueError('请填写订阅名称和有效的 HTTP(S) 地址')
    if edit.get('new'):
        if name in providers or name in policy_names(config) or name in BUILTINS:
            raise ValueError('订阅或代理名称已存在')
        providers[name] = {'type': 'http', 'path': routing.provider_cache(name), 'interval': 3600}
    elif providers[name].get('type') != 'http':
        raise ValueError('请选择 HTTP 节点订阅')
    providers[name] = {**providers[name], 'url': url}
    routing.merge_subscription_nodes(config)


def rename_policy(config, old, new):
    # Rule operands can contain commas (AND/OR) or equal the node name. Only the
    # policy before the optional trailing flags is a reference to this proxy.
    for rules in [config.get('rules', []), *config.get('sub-rules', {}).values()]:
        for index, rule in enumerate(rules):
            tokens = rule.split(',')
            if tokens[0].strip().upper() == 'SUB-RULE':
                continue
            pos = len(tokens) - 1
            while pos > 1 and tokens[pos].strip() in ('no-resolve', 'src', 'dst') and tokens[pos].strip() != old:
                pos -= 1
            if pos and tokens[pos].strip() == old:
                tokens[pos] = new
                rules[index] = ','.join(tokens)
    exclusions = config.get(routing.DOMAIN_EXCLUSIONS, {})
    if old in exclusions:
        exclusions[new] = exclusions.pop(old)
    if old in config.get(routing.DISABLED, []):
        config[routing.DISABLED] = [new if n == old else n for n in config[routing.DISABLED]]
    for group in config.get('proxy-groups', []):
        if group.get('default-selected') == old:
            group['default-selected'] = new
        if 'proxies' in group:
            group['proxies'] = [new if name == old else name for name in group['proxies']]
    for entry in [*config.get('proxies', []), *config.get('proxy-groups', []), *config.get('listeners', []),
                  *config.get('proxy-providers', {}).values(), *config.get('rule-providers', {}).values()]:
        for mapping in (entry, entry.get('override') or {}):
            for key in ('dialer-proxy', 'proxy'):
                if mapping.get(key) == old:
                    mapping[key] = new


def migrate_groups(config, selections=None):
    """Rename legacy managed groups and pin unambiguous group-wide bindings."""
    groups = {g['name']: g for g in config.get('proxy-groups', [])}
    selections = selections or {}
    old_ai_bindings = any(n in groups for n in ('AI', '🤖 AI'))
    for old, new in routing.ALIASES.items():
        if old not in groups:
            continue
        if new in policy_names(config):
            raise ValueError(f'无法将 {old} 改名为 {new}：名称已被使用')
        group = groups.pop(old)
        group['name'] = new
        groups[new] = group
        rename_policy(config, old, new)
        if selections.get(old):
            group['default-selected'] = selections[old]
    exits = routing.exits(config)
    current = selections.get('🤖 AI') or selections.get('AI')
    selected = current if current in exits else (exits[0] if len(exits) == 1 else None)
    if old_ai_bindings and selected:
        for row in reversed(list(bindings(config))):
            if row['target'] == routing.PROXY:
                edit_binding(config, dict(id=row['id'], ip=row['ip'], target=selected))


def edit_exit_note(config, edit):
    node = next((n for n in config.get('proxies', []) if n.get('name') == edit['name']), None)
    if node is None:
        raise ValueError('请选择已有出口')
    note = edit['note'].strip()
    if note:
        node[routing.EXIT_NOTE] = note
    else:
        node.pop(routing.EXIT_NOTE, None)


def edit_exit(config, edit):
    name = edit['name'].strip()
    old = edit.get('original')
    protocol = edit['type']
    server = edit['server'].strip()
    port = int(edit['port'])
    if not name or re.search(r'[,\r\n]', name) or name in BUILTINS:
        raise ValueError('请使用有效的出口名称，名称中不能包含逗号或换行')
    if protocol not in EDITABLE_TYPES or not server or not 1 <= port <= 65535:
        raise ValueError('请检查协议、服务器和端口')
    if old != name and name in policy_names(config):
        raise ValueError('出口名称已被节点或代理组使用')
    nodes = config.setdefault('proxies', [])
    if old is None:
        node = {}
        nodes.append(node)
    else:
        node = next(n for n in nodes if n['name'] == old and n['type'] in EDITABLE_TYPES)
        if old != name:
            rename_policy(config, old, name)
    node.update(name=name, type=protocol, server=server, port=port)
    if 'note' in edit:
        edit_exit_note(config, edit)
    for key in ('username', 'password', 'dialer-proxy'):
        value = edit.get(key, '')
        if key == 'dialer-proxy' and value and value == name:
            raise ValueError('前置代理不能选择出口自身')
        if value:
            node[key] = value
        elif key in node:
            del node[key]
    if edit.get('tls') or 'tls' in node:
        node['tls'] = bool(edit.get('tls'))
    if edit.get('deviceExit'):
        groups = config.setdefault('proxy-groups', [])
        pool = next((g for g in groups if g['name'] == routing.PROXY), None)
        if pool is None:
            if routing.PROXY in policy_names(config):
                raise ValueError('Proxy 已被节点占用')
            pool = {'name': routing.PROXY, 'type': 'select', 'proxies': []}
            groups.append(pool)
        members = pool.setdefault('proxies', [])
        if name not in members:
            members.append(name)
    if 'groups' in edit:
        for group in config.get('proxy-groups', []):
            members = group.get('proxies', [])
            if group['name'] in edit['groups'] and name not in members:
                group['proxies'] = [*members, name]
            elif group['name'] not in edit['groups'] and name in members:
                group['proxies'] = [member for member in members if member != name]


def edit_group(config, edit):
    groups = config.setdefault('proxy-groups', [])
    name, original = edit['name'].strip(), edit.get('original')
    if not name or ',' in name or (name != original and name in set(policy_names(config)) | BUILTINS):
        raise ValueError('请输入唯一的策略组名称')
    group = next((g for g in groups if g.get('name') == original), None) if original else {}
    if original in routing.REQUIRED and name != original:
        raise ValueError('固定策略组必须保留原名')
    if group is None:
        raise ValueError('策略组已变化，请重新打开')
    members, providers = edit['proxies'], edit['use']
    if original == routing.PROXY:
        removed = set(routing.exits(config)) - set(members)
        if any(r['target'] in removed for r in bindings(config)):
            raise ValueError('请先为使用该出口的设备更换绑定')

    if name in members or (original and original in members):
        raise ValueError('策略组不能包含自身')
    if original and name != original:
        rename_policy(config, original, name)
    if not original:
        groups.append(group)
    group.update(name=name, type=edit['type'])
    for key, items in [('proxies', members), ('use', providers)]:
        if items:
            group[key] = items
        else:
            group.pop(key, None)


def edit_binding(config, edit):
    rows = list(bindings(config))
    previous = next((r for r in rows if r['id'] == edit.get('id')), None)
    if edit.get('id') is not None and previous is None:
        raise ValueError('该网段绑定已变化，请重新选择')
    rules = config.setdefault('rules', [])
    notes = config.get(routing.NOTES, {})
    old_note = notes.pop(previous['ip'], '') if previous else ''
    subs = config.get('sub-rules') or {}
    old_key = previous['sub'] if previous else None
    if edit.get('remove'):
        if previous is None:
            raise ValueError('请选择要移除的网段绑定')
        del rules[previous['id']:previous['end']]
    else:
        first, last = address_range(edit['ip'])
        label = range_label(first, last)
        target = edit['target']
        if config.get('mode', 'rule').lower() != 'rule':
            raise ValueError('请先在配置项中将运行模式设为 rule')
        if target not in routing.exits(config):
            raise ValueError('请选择 Proxy 组内的具体出口')
        if any(row['ip'] == label and row != previous for row in rows):
            raise ValueError('这个网段已有绑定，请编辑原绑定')
        note = str(edit.get('note', old_note)).strip()
        if note:
            notes[label] = note
        if not previous or (previous['ip'], previous['target']) != (label, target):
            body = subs[old_key][:-1] if old_key else ([] if previous else PRIVATE_RULES)
            guarded = previous['reject'] if previous else True
            # Keep shared legacy sub-rules and their original exceptions intact.
            key = 'Gateway-Range-' + hashlib.sha256(f'{label} {target}'.encode()).hexdigest()[:16]
            desired = [*body, f'MATCH,{target}']
            while key in subs and subs[key] != desired:
                key += '_'
            subs[key] = desired
            config['sub-rules'] = subs
            new_rules = []
            for net in ipaddress.summarize_address_range(first, last):
                new_rules.append(f'SUB-RULE,(SRC-IP-CIDR,{net}),{key}')
                if guarded:
                    new_rules.append(f'SRC-IP-CIDR,{net},REJECT')
            start = previous['id'] if previous else rows[0]['id'] if rows else 0
            stop = previous['end'] if previous else start
            rules[start:stop] = new_rules
    if notes:
        config[routing.NOTES] = notes
    else:
        config.pop(routing.NOTES, None)
    if old_key and old_key.startswith('Gateway-Range-'):
        references = [*rules, *(r for group in subs.values() for r in group)]
        if not any(r.startswith('SUB-RULE,') and r.rsplit(',', 1)[-1].strip() == old_key for r in references):
            del subs[old_key]


def edit_option(config, edit):
    path = edit['path']
    root = path[0]
    fixed = legacy.NETWORK_OWNED.get(root)
    if root == 'hosts':
        fixed = (state.settings()['domain'],)
    protected = root in legacy.GATEWAY_KEYS and fixed is None
    if fixed:
        protected = (root in config or edit.get('value') != {}) if len(path) == 1 else path[1] in fixed
    if protected:
        raise ValueError('此配置由网关管理')
    parent = config
    for part in path[:-1]:
        # An imported YAML document can alias the same map/list in multiple places.
        # Copy only this branch so that an edit stays local to the selected path.
        child = parent[part].copy()
        parent[part] = child
        parent = child
    key, action = path[-1], edit['action']
    if action == 'remove':
        del parent[key]
    elif isinstance(parent, list):
        if action == 'add':
            parent.insert(key, edit['value'])
        else:
            previous = parent.pop(key)
            parent.insert(edit.get('position', key), previous if action == 'move' else edit['value'])
    else:
        if action == 'add' and key in parent:
            raise ValueError('这个配置项已存在')
        value = edit['value']
        if len(path) == 3 and root in ('proxies', 'proxy-groups') and key == 'name':
            old = parent.get(key)
            if not isinstance(value, str) or not value.strip() or ',' in value:
                raise ValueError('请输入有效的代理名称')
            if old != value:
                if value in policy_names(config) or value in BUILTINS:
                    raise ValueError('代理名称已被使用')
                if old:
                    rename_policy(config, old, value)
        parent[key] = value


def edit_rule(config, edit):
    path = edit['path']
    parent = config
    for part in path[:-1]:
        parent = parent[part]
    rules = parent.setdefault(path[-1], [])
    index = edit.get('index')
    if edit.get('remove'):
        edit_option(config, {'path': [*path, index], 'action': 'remove'})
        return
    kind = edit['type'].strip().upper()
    operand = edit['operand'].strip()
    payload = path[0] == 'rule-providers'
    behavior = config['rule-providers'][path[1]].get('behavior', 'classical') if payload else None
    if not kind or kind != 'MATCH' and not operand:
        raise ValueError('请填写匹配条件')
    if kind in ('DOMAIN', 'DOMAIN-SUFFIX', 'DOMAIN-WILDCARD') and re.search(r'[/\s,]', operand):
        raise ValueError('请填写域名，去掉协议、路径和空格')
    if kind in ('IP-CIDR', 'IP-CIDR6') or behavior == 'ipcidr':
        try:
            net = ipaddress.ip_network(operand, strict=False)
        except ValueError:
            raise ValueError('请输入有效的 IP 地址或 CIDR 网段') from None
        if kind == 'IP-CIDR6' and net.version != 6:
            raise ValueError('请输入 IPv6 地址或网段')
        operand = str(net)
    if behavior in ('domain', 'ipcidr'):
        value = operand
    else:
        parts = [kind]
        if kind != 'MATCH':
            parts.append(operand)
        if not payload:
            target = edit['target'].strip()
            if not target or ',' in target:
                raise ValueError('请选择规则策略')
            parts.append(target)
        parts.extend(edit.get('flags', []))
        value = ','.join(parts)
    position = int(edit['position']) - 1
    if not 0 <= position < len(rules) + (index is None):
        raise ValueError('规则顺序超出范围')
    edit_option(config, {'path': [*path, position if index is None else index],
                         'action': 'add' if index is None else 'set', 'value': value, 'position': position})


def edit_subscribed_domain(config, edit):
    group, provider = edit['target'], edit['provider']
    scope = config
    for part in edit['path']:
        scope = scope[part]
    parts, pos = routing.policy_slot(scope[edit['index']])
    if pos != 2 or [p.strip() for p in parts[:3]] != ['RULE-SET', provider, group]:
        raise ValueError('规则集引用已变化，请重新打开')
    if not edit.get('remove') and (edit['type'], edit['operand'].strip()) == (edit['originalType'], edit['originalDomain']):
        return
    group_domains.exclude(config, group, provider, edit['originalType'], edit['originalDomain'])
    if edit.get('remove'):
        return
    # A shared provider may be used in multiple scopes. Apply the local replacement at
    # each reference for this group, without changing the provider or other policies.
    scopes = [(['rules'], config.get('rules', []))]
    scopes += [(['sub-rules', key], rules) for key, rules in (config.get('sub-rules') or {}).items()]
    for path, rules in scopes:
        for index in reversed(range(len(rules))):
            parts, pos = routing.policy_slot(rules[index])
            if pos == 2 and [p.strip() for p in parts[:3]] == ['RULE-SET', provider, group]:
                edit_rule(config, dict(edit, path=path, index=None, position=index + 1))


def draft(data):
    text = data['content']
    if len(text.encode()) > 2 * 1024 * 1024:
        raise ValueError('配置文件超过 2 MB')
    try:
        config = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, 'problem_mark', None)
        where = f'（第 {mark.line + 1} 行）' if mark else ''
        raise ValueError(f'YAML 格式有误{where}') from None
    if not isinstance(config, dict):
        raise ValueError('请填写 Clash YAML 配置')
    original = deepcopy(config)
    migrate_groups(config)
    routing.merge_subscription_nodes(config)
    if data.get('upload'):
        legacy.preserve_gateway_settings(config, state.config())
        return {'content': yaml.safe_dump(config, allow_unicode=True, sort_keys=False), 'model': model(config)}
    if 'domainPage' in data:
        return group_domains.domain_page(config, data['domainPage'])
    edit = data.get('edit')
    if not edit:
        result = {'model': model(config)}
        if config != original:
            result['content'] = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
        return result
    if edit['kind'] == 'default-exit':
        target = edit['target']
        group = routing.pool(config)
        live = [] if target in group.get('proxies', []) else live_pool(config).get('all', [])
        routing.set_default(config, target, live)
        return {'model': model(config), 'content': yaml.safe_dump(config, allow_unicode=True, sort_keys=False)}
    change = {'provider': edit_provider, 'exit': edit_exit, 'note': edit_exit_note, 'binding': edit_binding,
              'option': edit_option, 'rule': edit_rule, 'subscription-domain': edit_subscribed_domain, 'group': edit_group, 'toggle-group': lambda cfg, e: routing.toggle(cfg, e['name'], e['enabled'])}[edit['kind']]
    change(config, edit)
    if edit['kind'] == 'group':
        routing.merge_subscription_nodes(config)
    if config != original:
        text = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
    return {'model': model(config), 'content': text}
