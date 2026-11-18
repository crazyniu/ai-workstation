"""Device exits and optional service groups in the editable Clash profile."""

PROXY = '🤖 PROXY'
RELAY = '🔗 PROXY-RELAY'
NOTES = 'x-gateway-ip-notes'
DISABLED = 'x-gateway-disabled-groups'
DOMAIN_EXCLUSIONS = 'x-gateway-domain-exclusions'
EXIT_NOTE = 'x-gateway-note'
REQUIRED = (PROXY, RELAY)
ALIASES = {name: RELAY for name in ('AI-RELAY', '🔗 AI-RELAY', 'Proxy-Reply', 'PROXY-RELAY')}
ALIASES.update({name: PROXY for name in ('AI', '🤖 AI', 'Proxy', 'PROXY')})


def policy_slot(rule):
    fields = rule.split(',')
    index = len(fields) - 1
    while index > 1 and fields[index].strip() in ('no-resolve', 'src', 'dst'):
        index -= 1
    return fields, index


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
