"""Edit a Clash YAML draft. Applying it is the existing revision-checked importer’s job."""
import hashlib
import ipaddress
import re
from copy import deepcopy
from urllib.parse import urlsplit

import yaml
import legacy
import state

from workstation_dns import PRIVATE_RULES

EDITABLE_TYPES = ('http', 'socks5')
BUILTINS = {'DIRECT', 'REJECT', 'REJECT-DROP', 'PASS', 'COMPATIBLE', 'GLOBAL'}
DIRECT_SOURCE = re.compile(r'SRC-IP-CIDR,\s*([^,]+),\s*([^,]+)(?:,\s*no-resolve)?', re.I)
SUB_SOURCE = re.compile(r'SUB-RULE,\s*\(SRC-IP-CIDR,\s*([^,)]+)\),\s*([^,]+)', re.I)


def bindings(config):
    rules = config.get('rules') or []
    subs = config.get('sub-rules') or {}
    index = 0
    while index < len(rules):
        rule = rules[index]
        if not isinstance(rule, str):
            index += 1
            continue
        sub = SUB_SOURCE.fullmatch(rule)
        match = sub or DIRECT_SOURCE.fullmatch(rule)
        if match:
            try:
                network = ipaddress.ip_network(match[1].strip(), strict=False)
            except ValueError:
                index += 1
                continue
            target = match[2].strip()
            key = target if sub else None
            end = index + 1
            if sub:
                body = subs.get(key, [])
                target = body[-1][6:] if body and isinstance(body[-1], str) and body[-1].startswith('MATCH,') else None
                fallback = DIRECT_SOURCE.fullmatch(rules[end]) if end < len(rules) and isinstance(rules[end], str) else None
                if fallback and fallback[1].strip() == match[1].strip() and fallback[2].strip() == 'REJECT':
                    end += 1
            if network.num_addresses == 1 and target:
                yield {'id': index, 'ip': str(network.network_address), 'target': target,
                       'sub': key, 'end': end}
            index = end
        else:
            index += 1


def policy_names(config):
    return [entry['name'] for section in ('proxies', 'proxy-groups') for entry in (config.get(section) or [])
            if isinstance(entry, dict) and isinstance(entry.get('name'), str)]


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
        if locked is not True:
            options[key] = ({k: v for k, v in value.items() if k not in locked}
                            if locked and isinstance(value, dict) else value)
    return {
        'providers': [{'name': name, 'url': entry.get('url', '')}
                      for name, entry in (config.get('proxy-providers') or {}).items()
                      if isinstance(entry, dict) and entry.get('type') == 'http'],
        'exits': [{key: node[key] for key in ('name', 'type', 'server', 'port', 'username', 'password',
                                              'dialer-proxy', 'tls') if key in node}
                  for node in nodes if node.get('type') in EDITABLE_TYPES],
        'bindings': [{k: row[k] for k in ('id', 'ip', 'target')} for row in bindings(config)],
        'targets': policy_names(config),
        'groups': [{'name': group['name'], 'members': group.get('proxies') or []} for group in groups],
        'options': options, 'fixed': fixed,
    }


def edit_provider(config, edit):
    name = edit['name'].strip()
    url = edit['url'].strip()
    parsed = urlsplit(url)
    if not name or parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise ValueError('请填写订阅名称和有效的 HTTP(S) 地址')
    providers = config.setdefault('proxy-providers', {})
    if edit.get('new'):
        if name in providers or name in policy_names(config) or name in BUILTINS:
            raise ValueError('订阅或代理名称已存在')
        cache = hashlib.sha256(name.encode()).hexdigest()[:16]
        providers[name] = {'type': 'http', 'path': f'./providers/{cache}.yaml', 'interval': 3600}
        config.setdefault('proxy-groups', []).append({'name': name, 'type': 'select', 'use': [name]})
    elif providers[name].get('type') != 'http':
        raise ValueError('请选择 HTTP 节点订阅')
    providers[name] = {**providers[name], 'url': url}


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
    for group in config.get('proxy-groups', []):
        if 'proxies' in group:
            group['proxies'] = [new if name == old else name for name in group['proxies']]
    for entry in [*config.get('proxies', []), *config.get('proxy-groups', []), *config.get('listeners', []),
                  *config.get('proxy-providers', {}).values(), *config.get('rule-providers', {}).values()]:
        for mapping in (entry, entry.get('override') or {}):
            for key in ('dialer-proxy', 'proxy'):
                if mapping.get(key) == old:
                    mapping[key] = new


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
    if 'groups' in edit:
        for group in config.get('proxy-groups', []):
            members = group.get('proxies', [])
            if group['name'] in edit['groups'] and name not in members:
                group['proxies'] = [*members, name]
            elif group['name'] not in edit['groups'] and name in members:
                group['proxies'] = [member for member in members if member != name]


def edit_binding(config, edit):
    rows = list(bindings(config))
    previous = next((r for r in rows if r['id'] == edit.get('id')), None)
    rules = config.setdefault('rules', [])
    if edit.get('remove'):
        if previous is None:
            raise ValueError('请选择已有绑定')
        del rules[previous['id']:previous['end']]
        return
    try:
        ip = ipaddress.ip_address(edit['ip'].strip())
    except ValueError:
        raise ValueError('请输入单个 IPv4 或 IPv6 地址') from None
    target = edit['target']
    if config.get('mode', 'rule').lower() != 'rule':
        raise ValueError('请先在配置项中将运行模式设为 rule')
    if target not in policy_names(config) and target not in ('DIRECT', 'REJECT') and not (previous and target == previous['target']):
        raise ValueError('请选择已有出口或代理组')
    if any(row != previous and row['ip'] == str(ip) for row in rows):
        raise ValueError('这个来源 IP 已有绑定，请编辑原绑定')
    cidr = f'{ip}/{ip.max_prefixlen}'
    if previous and previous['target'] == target and previous['ip'] == str(ip):
        return
    if previous and previous['sub'] is None:
        tokens = rules[previous['id']].split(',')
        tokens[1:3] = [cidr, target]
        rules[previous['id']] = ','.join(tokens)
        return

    subs = config.setdefault('sub-rules', {})
    key = previous['sub'] if previous else None
    if not previous or previous['target'] != target:
        body = subs[key][:-1] if previous else PRIVATE_RULES
        # Several clients may share the same named sub-rule. Give just this
        # client its own copy when changing its exit, retaining all exceptions.
        all_rules = [*rules, *(rule for group in subs.values() for rule in group)]
        shared = key and sum(r.partition(',')[0].strip().upper() == 'SUB-RULE' and r.rsplit(',', 1)[-1].strip() == key
                             for r in all_rules) > 1
        if not key or shared:
            base = 'WORKSTATION-EXIT-' + str(ip).replace('.', '-').replace(':', '-')
            key = base
            suffix = 2
            while key in subs:
                key = f'{base}-{suffix}'
                suffix += 1
        subs[key] = [*body, f'MATCH,{target}']
    dispatch = f'SUB-RULE,(SRC-IP-CIDR,{cidr}),{key}'
    if previous:
        rules[previous['id']] = dispatch
        if previous['end'] == previous['id'] + 2:
            rules[previous['id'] + 1] = f'SRC-IP-CIDR,{cidr},REJECT'
    else:
        rules[:0] = [dispatch, f'SRC-IP-CIDR,{cidr},REJECT']


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
    if data.get('upload'):
        legacy.preserve_gateway_settings(config, state.config())
        return {'content': yaml.safe_dump(config, allow_unicode=True, sort_keys=False), 'model': model(config)}
    edit = data.get('edit')
    if not edit:
        return {'model': model(config)}
    change = {'provider': edit_provider, 'exit': edit_exit, 'binding': edit_binding,
              'option': edit_option, 'rule': edit_rule}[edit['kind']]
    original = deepcopy(config)
    change(config, edit)
    if config != original:
        text = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
    return {'model': model(config), 'content': text}
