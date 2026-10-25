#!/usr/bin/python3
"""Apply the workstation's region before starting SSH and the desktop.

Optional container-internal region.json overrides WORKSTATION_* runtime values.
This lets existing containers change region without replacing their HOME/data.
"""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

DEFAULTS = {'country': 'SG', 'language': 'en', 'timezone': 'Asia/Singapore'}
VARIABLES = {key: 'WORKSTATION_' + key.upper() for key in DEFAULTS}
FORMAT_CATEGORIES = ('LC_NUMERIC', 'LC_TIME', 'LC_MONETARY', 'LC_PAPER',
                     'LC_NAME', 'LC_ADDRESS', 'LC_TELEPHONE',
                     'LC_MEASUREMENT', 'LC_IDENTIFICATION')


def select_region(environ, overrides, root=Path('/')):
    if not isinstance(overrides, dict) or set(overrides) - set(DEFAULTS):
        raise ValueError('region.json accepts only country, language and timezone')
    region = {key: overrides.get(key, environ.get(VARIABLES[key], default))
              for key, default in DEFAULTS.items()}
    if not all(isinstance(value, str) for value in region.values()):
        raise ValueError('Region values must be strings')
    country, language, timezone = (region[key] for key in DEFAULTS)
    if not re.fullmatch(r'[A-Z]{2}', country):
        raise ValueError('WORKSTATION_COUNTRY must be a two-letter uppercase country code')
    if not re.fullmatch(r'[a-z]{2,3}', language):
        raise ValueError('WORKSTATION_LANGUAGE must be a two/three-letter lowercase language code')
    locale = language + '_' + country
    # glibc has no en_TW: use English messages with Taiwan regional formats.
    formats = 'zh_TW' if locale == 'en_TW' else None
    if formats:
        locale = 'en_US'
    for source in {locale, formats} - {None}:
        if not (root / 'usr/share/i18n/locales' / source).is_file():
            raise ValueError('Unsupported language/country locale: ' + source)
    zones = (root / 'usr/share/zoneinfo').resolve()
    zone = zones / timezone
    if (not timezone or timezone.startswith('/') or '..' in timezone.split('/')
            or not re.fullmatch(r'[A-Za-z0-9_+./-]+', timezone)
            or not zone.resolve().is_relative_to(zones) or not zone.is_file()):
        raise ValueError('Unsupported IANA timezone: ' + timezone)
    with zone.open('rb') as stream:
        if stream.read(4) != b'TZif':
            raise ValueError('Timezone must name a compiled tzdata zone: ' + timezone)
    selected = {'LANG': locale + '.UTF-8', 'LC_ALL': locale + '.UTF-8',
                'LANGUAGE': locale + ':' + language, 'TZ': timezone}
    if formats:
        # LC_ALL must be empty so category-specific regional settings take effect.
        selected.update(LC_ALL='', LC_MESSAGES=selected['LANG'])
        selected.update({key: formats + '.UTF-8' for key in FORMAT_CATEGORIES})
    selected.update({VARIABLES[key]: value for key, value in region.items()})
    return selected


def configure_region(root=Path('/'), environ=None, run=subprocess.run):
    environ = dict(os.environ if environ is None else environ)
    config = root / 'etc/workstation/region.json'
    if config.is_symlink():
        raise ValueError('region.json must be a regular container-internal file')
    overrides = {}
    if config.exists():
        if not config.is_file() or config.stat().st_size > 4096:
            raise ValueError('region.json must be a JSON object of at most 4096 bytes')
        overrides = json.loads(config.read_text())
    # Validate everything before modifying the system configuration.
    selected = select_region(environ, overrides, root)
    tool_env = dict(environ, LANG='C.UTF-8', LC_ALL='C.UTF-8', LANGUAGE='C')
    locales = run(['locale', '-a'], env=tool_env, check=True,
                  text=True, stdout=subprocess.PIPE).stdout.splitlines()
    normalize = lambda name: name.lower().replace('-', '')
    required = {value for key, value in selected.items()
                if value and (key == 'LANG' or key.startswith('LC_'))}
    for locale in sorted(required):
        if normalize(locale) not in {normalize(name) for name in locales}:
            source = locale.split('.')[0]
            run(['localedef', '-i', source, '-f', 'UTF-8', locale],
                env=tool_env, check=True, stdout=subprocess.DEVNULL)
    (root / 'etc/default/locale').write_text(''.join(
        key + '=' + value + '\n' for key, value in selected.items()
        if key in ('LANG', 'LANGUAGE') or key.startswith('LC_')))
    # PAM uses /etc/environment for SSH; preserve unrelated deployment settings.
    path = root / 'etc/environment'
    previous = path.read_text().splitlines() if path.exists() else []
    managed = set(selected) | set(FORMAT_CATEGORIES) | {'LC_MESSAGES'}
    retained = [line for line in previous
                if line.split('=', 1)[0].strip() not in managed]
    path.write_text('\n'.join(retained + [key + '=' + value
                                         for key, value in selected.items()]) + '\n')
    profile = root / 'etc/profile.d/workstation-region.sh'
    profile.write_text('# Generated by workstation initialization; edit /etc/workstation/region.json.\n'
                       + 'unset ' + ' '.join((*FORMAT_CATEGORIES, 'LC_MESSAGES')) + '\n'
                       + ''.join('export ' + key + '=' + shlex.quote(value) + '\n'
                                 for key, value in selected.items()))
    profile.chmod(0o644)
    localtime = root / 'etc/localtime'
    if localtime.is_symlink() or localtime.exists():
        localtime.unlink()
    localtime.symlink_to('/usr/share/zoneinfo/' + selected['TZ'])
    (root / 'etc/timezone').write_text(selected['TZ'] + '\n')
    return selected


if __name__ == '__main__':
    try:
        if os.getuid() != 0:
            raise ValueError('Region initialization must run as root')
        print(json.dumps(configure_region()))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('Region initialization failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
