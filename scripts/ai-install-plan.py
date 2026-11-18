"""Check the effective Compose plan before the default AI installation starts."""
import json
import subprocess
import sys


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True)


def main(compose_file, role):
    engine = docker('info', '--format', '{{.OSType}}/{{.OperatingSystem}}').strip()
    if not engine.startswith('linux/') or 'docker desktop' in engine.lower():
        sys.exit('当前 Docker Engine 不支持本方案的独立 LAN 地址。请先取得用户对替代方案的同意。')

    config = json.loads(docker('compose', '--env-file', '.env', '-f', compose_file,
                               'config', '--format', 'json'))
    services = config['services']
    expected = {'gateway', 'workstation'} if role == 'all' else {role}
    if set(services) != expected:
        sys.exit('实际部署角色与本次安装范围不符。请先取得用户同意。')

    gateway_ip = '192.168.1.250'
    workstation_ip = '192.168.1.251'
    for name, service in services.items():
        if name == 'gateway':
            image = 'ghcr.io/crazyniu/ai-workstation-gateway:latest'
            address = service['environment']['GATEWAY_LAN_ADDRESS'].split('/')[0]
            desired = gateway_ip
            peer = service['environment']['GATEWAY_BLOCK_DIRECT_CLIENTS']
            expected_peer = workstation_ip
        else:
            image = 'ghcr.io/crazyniu/ai-workstation:latest'
            address = service['networks']['workstation_lan']['ipv4_address']
            desired = workstation_ip
            peer = config['networks']['workstation_lan']['ipam']['config'][0]['gateway']
            expected_peer = gateway_ip
        for label, actual, default in [('镜像', service['image'], image),
                                       ('LAN 地址', address, desired),
                                       ('对端地址', peer, expected_peer)]:
            if actual != default:
                sys.exit(f'{name} 的{label}为 {actual}，默认值为 {default}。请先取得用户同意。')
        print(f'{name}  {image}  {address}')


if __name__ == '__main__':
    main(*sys.argv[1:])
