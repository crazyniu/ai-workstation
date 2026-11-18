"""Browse concrete domain matches, keeping subscribed rule sets editable through local exceptions."""
from functools import lru_cache
import re
import subprocess

import yaml
import legacy
import routing_groups as routing
import state

TYPES = ('DOMAIN', 'DOMAIN-SUFFIX', 'DOMAIN-KEYWORD', 'DOMAIN-WILDCARD')
PAGE_SIZES = (10, 20, 50, 100)


def domain_entry(line, behavior):
    if not isinstance(line, str):
        return None
    line = line.strip()
    if not line or line.startswith(('#', '!')):
        return None
    if behavior == 'classical':
        kind, _, name = line.partition(',')
        if kind not in TYPES:
            return None
    elif line.startswith('+.'):
        kind, name = 'DOMAIN-SUFFIX', line[2:]
    elif line.startswith('.'):
        kind, name = 'DOMAIN-WILDCARD', '*' + line
    else:
        kind, name = ('DOMAIN-WILDCARD' if '*' in line or '?' in line else 'DOMAIN'), line
    if not name or re.search(r'[\s,()/]', name):
        return None
    return kind, name


@lru_cache(maxsize=6)
def read_cache(path, modified, size, fmt, behavior):
    if fmt == 'mrs':
        process = subprocess.run([legacy.MIHOMO, 'convert-ruleset', behavior, 'mrs', str(path), '/dev/stdout'],
                                 capture_output=True, check=True, timeout=20)
        lines = process.stdout.decode().splitlines()
    elif fmt == 'text':
        lines = path.read_text().splitlines()
    else:
        lines = (yaml.safe_load(path.read_text()) or {}).get('payload', [])
    return tuple(entry for line in lines if (entry := domain_entry(line, behavior)))


def entries(name, provider, installed):
    behavior = provider.get('behavior', 'classical')
    if behavior not in ('domain', 'classical'):
        return ()
    if provider.get('type') == 'inline' or isinstance(provider.get('payload'), list):
        return (entry for line in provider.get('payload', []) if (entry := domain_entry(line, behavior)))
    # Resolve only a previously configured, installed cache. Drafts cannot select a file to read.
    current = installed.get(name, {})
    if not current.get('path') or any(current.get(k) != provider.get(k) for k in ('path', 'url', 'format', 'behavior')):
        raise ValueError('规则集尚未下载')
    path = (legacy.MIHOMO_DIR / current['path']).resolve()
    if not path.is_relative_to(legacy.MIHOMO_DIR.resolve()) or path in (legacy.MIHOMO_CONFIG.resolve(), (legacy.MIHOMO_DIR / '.gateway-effective.yaml').resolve()):
        raise ValueError('规则集路径无效')
    stat = path.stat()
    return read_cache(path, stat.st_mtime_ns, stat.st_size, current.get('format', 'yaml'), behavior)


def domain_page(config, request):
    group = request['group']
    search = request.get('search', '').casefold().strip()
    limit = int(request.get('limit', 20))
    if limit not in PAGE_SIZES:
        raise ValueError('每页数量无效')
    page = max(0, int(request.get('page', 0)))
    installed = (state.config().get('rule-providers') or {})
    providers = config.get('rule-providers') or {}
    excludes = (config.get(routing.DOMAIN_EXCLUSIONS) or {}).get(group, {})
    result, missing, seen = [], [], set()
    total = 0
    scopes = [(['rules'], config.get('rules') or [])]
    visited = set()
    for scope, rules in scopes:
        for index, text in enumerate(rules):
            parts, end = routing.policy_slot(text)
            kind = parts[0].strip().upper()
            target = parts[end].strip()
            if kind == 'SUB-RULE' and target not in visited:
                visited.add(target)
                scopes.append((['sub-rules', target], (config.get('sub-rules') or {}).get(target, [])))
            if target != group or end != 2:
                continue
            value = parts[1].strip()
            provider = value if kind == 'RULE-SET' else None
            if provider:
                if provider in seen:
                    continue
                seen.add(provider)
                try:
                    domains = entries(provider, providers.get(provider, {}), installed)
                except (OSError, ValueError, subprocess.SubprocessError, yaml.YAMLError):
                    missing.append(provider)
                    continue
            else:
                domains = [(kind, value)] if kind in TYPES else []
            blocked = set(excludes.get(provider, []))
            for match, domain in domains:
                if search not in domain.casefold() or f'{match},{domain}' in blocked:
                    continue
                if page * limit <= total < (page + 1) * limit:
                    result.append(dict(type=match, domain=domain, path=scope, index=index, provider=provider))
                total += 1
    return dict(rows=result, total=total, missing=missing)


def exclude(config, group, provider, kind, domain):
    if kind not in TYPES or not domain or re.search(r'[\s,()/]', domain):
        raise ValueError('域名匹配条件无效')
    items = config.setdefault(routing.DOMAIN_EXCLUSIONS, {}).setdefault(group, {}).setdefault(provider, [])
    rule = f'{kind},{domain}'
    if rule not in items:
        items.append(rule)
