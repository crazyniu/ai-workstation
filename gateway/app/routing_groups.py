"""Device exits and optional service groups in the editable Clash profile."""

import hashlib

PROXY = '🤖 PROXY'
RELAY = '🔗 PROXY-RELAY'
NOTES = 'x-gateway-ip-notes'
DISABLED = 'x-gateway-disabled-groups'
DOMAIN_EXCLUSIONS = 'x-gateway-domain-exclusions'
EXIT_NOTE = 'x-gateway-note'
REQUIRED = (PROXY, RELAY)
SUBSCRIPTION_INFO_FILTER = (
    r'(?i)免费|流量|到期|过期|過期|有效期|套餐|重置|更新订阅|更新訂閱|'
    r'\b(?:expire[sd]?|expiration|traffic[ _-]*(?:left|remaining)|remaining[ _-]*(?:traffic|data))\b'
)
ALIASES = {name: RELAY for name in ('AI-RELAY', '🔗 AI-RELAY', 'Proxy-Reply', 'PROXY-RELAY')}
ALIASES.update({name: PROXY for name in ('AI', '🤖 AI', 'Proxy', 'PROXY')})


def policy_slot(rule):
    fields = rule.split(',')
    index = len(fields) - 1
    while index > 1 and fields[index].strip() in ('no-resolve', 'src', 'dst'):
        index -= 1
    return fields, index


def provider_cache(name):
    return './providers/' + hashlib.sha256(name.encode()).hexdigest()[:16] + '.yaml'


def policy_in_use(config, name):
    groups = config.get('proxy-groups') or []
    if any(name in (g.get('proxies') or []) or g.get('default-selected') == name for g in groups):
        return True
    rulesets = [config.get('rules') or [], *(config.get('sub-rules') or {}).values()]
    for rules in rulesets:
        for rule in rules:
            fields, index = policy_slot(rule)
            if fields[0].strip().upper() != 'SUB-RULE' and fields[index].strip() == name:
                return True
    for entry in [*(config.get('proxies') or []), *(config.get('listeners') or []),
                  *(config.get('proxy-providers') or {}).values(), *(config.get('rule-providers') or {}).values()]:
        for options in (entry, entry.get('override') or {}):
            if options.get('proxy') == name or options.get('dialer-proxy') == name:
                return True
    return name in (config.get(DISABLED) or []) or name in (config.get(DOMAIN_EXCLUSIONS) or {})


def merge_subscription_nodes(config, removed=()):
    providers = config.get('proxy-providers') or {}
    if not providers and not removed:
        return
    groups = config.get('proxy-groups') or []
    # Recognize the exact selector and cache path created by the previous editor.
    # A selector used by another policy must retain its name and references.
    for group in list(groups):
        name = group['name']
        if (name in providers and name not in REQUIRED and group == {'name': name, 'type': 'select', 'use': [name]}
                and providers[name].get('path') == provider_cache(name) and not policy_in_use(config, name)):
            groups.remove(group)
    if not groups and providers:
        groups = [{'name': PROXY, 'type': 'select'}]
        config['proxy-groups'] = groups

    for provider in providers.values():
        current = provider.get('exclude-filter') or ''
        filters = current.split('`') if current else []
        if SUBSCRIPTION_INFO_FILTER not in filters:
            provider['exclude-filter'] = '`'.join([*filters, SUBSCRIPTION_INFO_FILTER])

    sources = list(providers)
    for group in groups:
        if group['type'] not in ('select', 'url-test', 'fallback', 'load-balance'):
            if removed and group.get('use'):
                group['use'] = [name for name in group['use'] if name not in removed]
            continue
        if group.pop('include-all', False):
            group['include-all-proxies'] = True
        group.pop('include-all-providers', None)
        if sources:
            group['use'] = sources.copy()
            if group.pop('x-gateway-empty-subscription', False) and group.get('proxies') == ['REJECT']:
                del group['proxies']
        else:
            group.pop('use', None)
            if not group.get('proxies') and not group.get('include-all-proxies'):
                group['proxies'] = ['REJECT']
                group['x-gateway-empty-subscription'] = True


def pool(config):
    return next((g for g in config.get('proxy-groups', []) if g['name'] == PROXY), {})


def set_default(config, target, live_members=()):
    group = pool(config)
    if group.get('type') != 'select':
        raise ValueError('AI 默认出口需要 Proxy 手动选择组')
    if target not in group.get('proxies', []) and target not in live_members:
        raise ValueError('请选择 Proxy 组内的出口')
    group['default-selected'] = target


def exits(config):
    group = pool(config)
    nodes = {n['name'] for n in config.get('proxies', []) if n.get('name')}
    return [name for name in group.get('proxies', []) if name in nodes]


def default_policy(config):
    for rule in config.get('rules', []):
        fields, i = policy_slot(rule)
        if i and fields[0].strip().upper() == 'MATCH':
            return fields[i].strip()
    return ''


def toggle(config, name, enabled):
    if name in REQUIRED or name not in {g['name'] for g in config.get('proxy-groups', [])}:
        raise ValueError('请选择可选策略组')
    if not enabled and not default_policy(config):
        raise ValueError('请先添加 MATCH 默认分流规则')
    disabled = [n for n in config.get(DISABLED, []) if n != name]
    if not enabled:
        disabled.append(name)
    if disabled:
        config[DISABLED] = disabled
    else:
        config.pop(DISABLED, None)


def apply_switches(config):
    """Keep definitions for re-enabling and for explicit transport dependencies."""
    config.pop(NOTES, None)
    for node in config.get('proxies', []):
        node.pop(EXIT_NOTE, None)
    excludes = config.pop(DOMAIN_EXCLUSIONS, {})
    if excludes:
        for rules in [config.get('rules', []), *(config.get('sub-rules') or {}).values()]:
            for index, rule in enumerate(rules):
                parts, pos = policy_slot(rule)
                if parts[0].upper() != 'RULE-SET' or pos != 2:
                    continue
                target = parts[pos].strip()
                exceptions = excludes.get(target, {}).get(parts[1].strip(), [])
                if exceptions:
                    original = ','.join(parts[:pos] + parts[pos + 1:])
                    conditions = ','.join([f'({original})', *[f'(NOT,(({r})))' for r in exceptions]])
                    rules[index] = f'AND,({conditions}),{target}'
    disabled = set(config.pop(DISABLED, [])) - set(REQUIRED)
    if not disabled:
        return
    default = default_policy(config)
    if not default:
        raise ValueError('关闭分组需要 MATCH 默认分流规则')
    for group in config.get('proxy-groups', []):
        if group['name'] in disabled:
            group['hidden'] = True
        # Hide switched-off choices in selection menus. A group whose only
        # member is a transport dependency still needs that member to function.
        members = group.get('proxies', [])
        keep = [member for member in members if member not in disabled]
        if keep and len(keep) != len(members):
            group['proxies'] = keep
    for rules in [config.get('rules', []), *(config.get('sub-rules') or {}).values()]:
        for index, rule in enumerate(rules):
            fields, i = policy_slot(rule)
            if i and fields[0].strip().upper() != 'SUB-RULE' and fields[i].strip() in disabled:
                fields[i] = default
                rules[index] = ','.join(fields)
