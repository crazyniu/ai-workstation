"""Check the effective Compose plan before the default AI installation starts."""
import json
import os
from pathlib import Path
import re
import tempfile
import subprocess
import sys


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True)


PRESETS = {
    'SG': ('en', 'Asia/Singapore'),
    'TW': ('zh', 'Asia/Taipei'),
    'US': ('en', 'America/Los_Angeles'),
}


def confirmed_region(role):
    country = os.environ.get('AI_INSTALL_COUNTRY', '').strip().upper()
    if not country:
        if not sys.stdin.isatty():
            sys.exit('Ask the user to choose a country before installation. Pass their answer in AI_INSTALL_COUNTRY.')
        print('1. Singapore (English)   2. Taiwan (Traditional Chinese)   3. United States (English, Los Angeles)')
        choice = input('Select a number or enter an ISO country code: ').strip().upper()
        country = {'1': 'SG', '2': 'TW', '3': 'US'}.get(choice, choice)
    if not re.fullmatch(r'[A-Z]{2}', country):
        sys.exit('A two-letter country code is required.')
    if country in PRESETS:
        language, timezone = PRESETS[country]
    else:
        language = os.environ.get('AI_INSTALL_LANGUAGE', '')
        timezone = os.environ.get('AI_INSTALL_TIMEZONE', '')
        if sys.stdin.isatty():
            language = language or input('Language code: ').strip()
            timezone = timezone or input('IANA time zone: ').strip()
        if not re.fullmatch(r'[a-z]{2,3}', language) or not re.fullmatch(r'[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)+|UTC', timezone):
            sys.exit('Confirm the language and IANA time zone for this country before installing.')
    values = {}
    if role in ('gateway', 'all'):
        values.update(GATEWAY_LOCALE=f'{language}_{country}.UTF-8', GATEWAY_TIMEZONE=timezone)
    if role in ('workstation', 'all'):
        values.update(WORKSTATION_COUNTRY=country, WORKSTATION_LANGUAGE=language, WORKSTATION_TIMEZONE=timezone)
    if any(key in os.environ and os.environ[key] != value for key, value in values.items()):
        sys.exit('Shell region variables conflict with the confirmed country. Remove those overrides before deploying.')
    return values


def save_region(values):
    path = Path('.env')
    content = path.read_text(encoding='utf-8')
    for key, value in values.items():
        line = f'{key}={value}'
        pattern = rf'^(?:export[ \t]+)?{key}[ \t]*=.*$'
        content, count = re.subn(pattern, line, content, flags=re.MULTILINE)
        if not count:
            content = content.rstrip('\n') + '\n' + line + '\n'
    with tempfile.TemporaryDirectory(dir=path.parent) as folder:
        staged = Path(folder) / '.env'
        staged.touch(mode=0o600)
        staged.write_text(content, encoding='utf-8')
        os.replace(staged, path)


def main(compose_file, role):
    region = confirmed_region(role)
    engine = docker('info', '--format', '{{.OSType}}/{{.OperatingSystem}}').strip()
    if not engine.startswith('linux/') or 'docker desktop' in engine.lower():
        sys.exit('当前 Docker Engine 不支持本方案的独立 LAN 地址。请先取得用户对替代方案的同意。')

    os.environ.update(region)
    config = json.loads(docker('compose', '--env-file', '.env', '-f', compose_file,
                               'config', '--format', 'json'))
    services = config['services']
    expected = {'gateway', 'workstation'} if role == 'all' else {role}
    if 'workstation' in expected:
        expected.add('workstation-network')
    if set(services) != expected:
        sys.exit('实际部署角色与本次安装范围不符。请先取得用户同意。')

    gateway_ip = '192.168.1.250'
    workstation_ip = '192.168.1.251'
    for name, service in services.items():
        if name == 'workstation-network':
            continue
        if name == 'gateway':
            image = 'ghcr.io/crazyniu/ai-workstation-gateway:latest'
            address = service['environment']['GATEWAY_LAN_ADDRESS'].split('/')[0]
            desired = gateway_ip
            peer = service['environment']['GATEWAY_BLOCK_DIRECT_CLIENTS']
            expected_peer = workstation_ip
            if workstation_ip not in service['environment'].get('GATEWAY_ISOLATED_CLIENTS', '').split():
                sys.exit('网关的隔离来源必须包含指定的工作站 IP。')
        else:
            image = 'ghcr.io/crazyniu/ai-workstation:latest'
            owner = services['workstation-network']
            if service.get('network_mode') != 'service:workstation-network' or owner['image'] != image:
                sys.exit('工作站必须使用同版本镜像创建的隔离网络。')
            address = owner['networks']['workstation_lan']['ipv4_address']
            desired = workstation_ip
            peer = config['networks']['workstation_lan']['ipam']['config'][0]['gateway']
            expected_peer = gateway_ip
        for label, actual, default in [('镜像', service['image'], image),
                                       ('LAN 地址', address, desired),
                                       ('对端地址', peer, expected_peer)]:
            if actual != default:
                sys.exit(f'{name} 的{label}为 {actual}，默认值为 {default}。请先取得用户同意。')
        print(f'{name}  {image}  {address}')
        prefix = name.upper() + '_'
        if any(service['environment'].get(key) != value for key, value in region.items() if key.startswith(prefix)):
            sys.exit(f'{name} does not use the confirmed region in the effective Compose plan.')
    save_region(region)
    print('Confirmed region:', ', '.join(f'{key}={value}' for key, value in region.items()))



if __name__ == '__main__':
    main(*sys.argv[1:])
