#!/usr/bin/env python3
"""Install dedicated Linux services without Docker; preview unless --apply is given."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import platform
import pwd
import grp
import shutil
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'gateway/app'))
from releases import architecture


def run(*command, **kwargs):
    subprocess.run(command, check=True, **kwargs)


def preflight(role, config, system=Path('/')):
    if platform.system() != 'Linux':
        raise ValueError('Native installation requires Linux. Use Docker Desktop on Windows/macOS.')
    # Userland architecture, including 32-bit userland on a 64-bit kernel.
    arch = architecture(subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip())
    release = dict(line.split('=', 1) for line in (system/'etc/os-release').read_text().splitlines() if '=' in line)
    distro = release.get('ID', '').strip('"')
    version = release.get('VERSION_ID', '').strip('"')
    minimum = {'debian': 12, 'ubuntu': 24}
    if distro not in minimum or int(version.split('.')[0]) < minimum[distro]:
        raise ValueError('Automatic package provisioning needs Debian 12+ or Ubuntu 24.04+. Other Linux distributions can use Docker or install the documented dependencies manually.')
    locks = json.loads((ROOT/'gateway/components.lock.json').read_text())['architectures']
    if role in ('all', 'gateway') and arch not in locks:
        raise ValueError('One or more gateway vendors have no pinned Linux release for ' + arch)
    if role in ('all', 'workstation') and arch not in ('amd64', 'arm64'):
        raise ValueError('Codex and Claude provide Linux binaries for amd64/arm64; no upstream release for ' + arch)
    paths = ['etc/ai-workstation-native.env']
    ports = []
    users = []
    if role in ('all', 'gateway'):
        paths += ['opt/gateway', 'var/lib/ai-gateway', 'run/gateway', 'run/tailscale',
                  'etc/systemd/system/ai-gateway.service']
        ports += [8080, 2223, 7890, 7891, 1053, 1153, 8787, 9090, 3000, 41641]
        # An existing tailscaled owns this socket even when it has no listener.
        if shutil.which('tailscaled'):
            raise ValueError('Existing host Tailscale detected; retain it and use Docker isolation for this gateway.')
    if role in ('all', 'workstation'):
        paths += ['opt/workstation', 'opt/node', 'etc/workstation', 'home/dev',
                  'usr/local/libexec/workstation-glycin', 'tmp/.X11-unix/X1',
                  'etc/systemd/system/ai-workstation.service']
        for name in ('node', 'npm', 'npx', 'uv', 'uvx', 'codex', 'claude', 'godot',
                     'workstation-mcp', 'unity-mcp', 'workstation-entrypoint',
                     'workstation-vnc', 'workstation-desktop', 'configure-workstation-exit-dns', 'reset-claude-user'):
            paths.append('usr/local/bin/' + name)
        paths += ['etc/apt/sources.list.d/workstation-vscode.list',
                  'etc/apt/sources.list.d/workstation-chrome.list',
                  'usr/share/keyrings/workstation-vscode.gpg', 'usr/share/keyrings/workstation-chrome.gpg']
        users = [('dev', 1100)]
        ports += [2222, 5901, 6080]
    for relative in paths:
        path = system / relative
        if path.exists() or path.is_symlink():
            raise ValueError('Existing installation/state must be preserved: /' + relative)
    for name, uid in users:
        for lookup, value in [(pwd.getpwnam, name), (pwd.getpwuid, uid), (grp.getgrnam, name), (grp.getgrgid, uid)]:
            try:
                lookup(value)
            except KeyError:
                continue
            raise ValueError('Existing account/group conflicts with dedicated dev UID/GID 1100')
    for port in ports:
        for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
            with socket.socket(socket.AF_INET, kind) as probe:
                try:
                    probe.bind(('0.0.0.0', port))
                except OSError:
                    raise ValueError('Existing listener conflicts with required port ' + str(port)) from None
    if config:
        if config.is_symlink() or not config.is_file() or config.stat().st_mode & 0o077:
            raise ValueError('Use a regular private config file with mode 600')
        allowed = {line.split('=', 1)[0] for line in (ROOT/'native/native.env.example').read_text().splitlines() if line and not line.startswith('#')}
        present = set()
        for line in config.read_text().splitlines():
            if not line or line.startswith('#'):
                continue
            key, separator, value = line.partition('=')
            if not separator or key not in allowed or not value or any(c in value for c in '\x00\r\n'):
                raise ValueError('Invalid native configuration entry; use native/native.env.example')
            present.add(key)
        required = set()
        if role in ('all', 'workstation'):
            required |= {'DEV_PASSWORD', 'VNC_PASSWORD'}
        if role in ('all', 'gateway'):
            required |= {'GATEWAY_ADMIN_PASSWORD', 'GATEWAY_CONTAINER_USER'}
        if not required <= present:
            raise ValueError('Missing required native configuration fields')
    return arch


@contextlib.contextmanager
def prevent_package_service_start():
    # Package installation must not auto-start or restart host SSH/nginx/supervisor.
    policy = Path('/usr/sbin/policy-rc.d')
    saved = policy.read_bytes() if policy.exists() else None
    mode = policy.stat().st_mode & 0o777 if saved is not None else None
    if policy.is_symlink():
        raise ValueError('Inspect existing policy-rc.d symlink before native provisioning')
    try:
        policy.write_text('#!/bin/sh\nexit 101\n')
        policy.chmod(0o755)
        yield
    finally:
        if saved is None:
            policy.unlink(missing_ok=True)
        else:
            policy.write_bytes(saved)
            policy.chmod(mode)


def unit(name, command, environment):
    text = '[Unit]\nDescription=AI ' + name + '\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=simple\nNoNewPrivileges=true\nEnvironmentFile=/etc/ai-workstation-native.env\n'
    text += ''.join('Environment=' + key + '=' + value + '\n' for key, value in environment.items())
    text += 'ExecStart=' + command + '\nRestart=on-failure\nRestartSec=5\nKillMode=control-group\nTimeoutStopSec=30\n\n[Install]\nWantedBy=multi-user.target\n'
    Path('/etc/systemd/system').mkdir(parents=True, exist_ok=True)
    Path('/etc/systemd/system/ai-' + name + '.service').write_text(text)


def install(role, config, arch, start):
    env = dict(os.environ, DEBIAN_FRONTEND='noninteractive', WORKSTATION_INSTALL_MODE='native')
    target = Path('/etc/ai-workstation-native.env')
    shutil.copyfile(config, target)
    target.chmod(0o600)
    if role in ('all', 'gateway'):
        run('apt-get', 'update', env=env)
        run('apt-get', 'install', '-y', '--no-install-recommends', 'nginx', 'supervisor', 'python3', 'python3-yaml', 'ca-certificates', 'iproute2', 'iptables', 'dnsutils', 'curl', 'procps', 'openssh-server', 'git', 'gh', env=env)
        run('python3', str(ROOT/'gateway/scripts/fetch-components.py'), arch)
        dest = Path('/opt/gateway')
        dest.mkdir()
        for name in ('app', 'runtime', 'web', 'seed', 'licenses'):
            shutil.copytree(ROOT/'gateway'/name, dest/name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store'))
        shutil.copyfile(ROOT/'gateway/components.lock.json', dest/'components.lock.json')
        shutil.copyfile(ROOT/'gateway/NOTICE', dest/'NOTICE')
        unit('gateway', '/bin/bash /opt/gateway/runtime/start', {
            'DATA_DIR': '/var/lib/ai-gateway', 'GATEWAY_INSTALL_MODE': 'native',
            'GATEWAY_MODE': 'false', 'GATEWAY_TAILSCALE_TUN': 'userspace-networking',
            'GATEWAY_WEB_PORT': '8080', 'GATEWAY_SSH_PORT': '2223', 'GATEWAY_BIND_ADDRESS': '127.0.0.1',
            'GATEWAY_DNS_PORT': '1053', 'GATEWAY_CORE_DNS_LISTEN': '127.0.0.1:1153', 'GATEWAY_CORE_DNS_UPSTREAM': '127.0.0.1:1153'})
    if role in ('all', 'workstation'):
        dest = Path('/opt/workstation')
        dest.mkdir()
        for name in ('scripts', 'mcp', 'unity', 'desktop', 'web-desktop', 'licenses'):
            shutil.copytree(ROOT/'workstation'/name, dest/name, ignore=shutil.ignore_patterns('node_modules', '__pycache__', '*.pyc', '.DS_Store'))
        shutil.copyfile(ROOT/'workstation/versions.env', dest/'versions.env')
        shutil.copytree(ROOT/'workstation/desktop/home-template', dest/'home-template', ignore=shutil.ignore_patterns('.DS_Store'))
        shutil.copytree(ROOT/'workstation/runtime', '/etc/workstation')
        run('bash', str(dest/'scripts/install-system.sh'), env=env)
        # Official Node archive, pinned to the same version as the container.
        run('bash', str(dest/'scripts/install-node.sh'), env=env)
        run('bash', str(dest/'scripts/install-tools.sh'), env=env)
        run('bash', str(dest/'scripts/install-runtime.sh'), env=env)
        ssh = Path('/etc/workstation/sshd_config')
        ssh.write_text(ssh.read_text().replace('Port 22', 'Port 2222\nListenAddress 127.0.0.1').replace('/etc/ssh/keys/', '/etc/workstation/ssh-keys/').replace('PermitRootLogin yes', 'PermitRootLogin no') + '\nAllowUsers dev\n')
        supervisor = Path('/etc/workstation/supervisord.conf')
        supervisor.write_text(supervisor.read_text().replace('command=/usr/sbin/sshd -D -e', 'command=/usr/sbin/sshd -D -e -f /etc/workstation/sshd_config').replace('/run/supervisord.pid', '/run/workstation-supervisord.pid').replace('files=/etc/supervisor/conf.d/*.conf', 'files=/etc/workstation/conf.d/*.conf'))
        Path('/etc/workstation/conf.d').mkdir()
        profile = Path('/home/dev/.profile')
        profile.write_text(profile.read_text() + '\n[ ! -r /etc/workstation/region.sh ] || . /etc/workstation/region.sh\n')
        unit('workstation', '/usr/local/bin/workstation-entrypoint', {'WORKSTATION_INSTALL_MODE': 'native', 'WORKSTATION_SSH_PORT': '2222', 'WORKSTATION_BIND_ADDRESS': '127.0.0.1', 'NOVNC_BIND': '127.0.0.1'})
    if start:
        run('systemctl', 'daemon-reload')
        for name in (('gateway', 'workstation') if role == 'all' else (role,)):
            run('systemctl', 'enable', '--now', 'ai-' + name + '.service')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', choices=('all', 'gateway', 'workstation'), default='all')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--no-start', action='store_true', help='Provision only; useful for disposable integration tests')
    args = parser.parse_args()
    arch = preflight(args.role, args.config)
    print(f'Native Linux {arch}: {args.role}; dedicated /opt paths, systemd units and internal state. Host root password and host SSH/nginx configuration are retained.')
    if not args.apply:
        print('Preview complete. Supply --config PRIVATE_FILE --apply to install.')
        return
    if os.getuid() != 0 or not args.config:
        raise ValueError('--apply requires root and --config PRIVATE_FILE')
    if not args.no_start and not Path('/run/systemd/system').is_dir():
        raise ValueError('Automatic service startup requires systemd; use --no-start for provisioning only')
    with prevent_package_service_start():
        install(args.role, args.config.resolve(), arch, not args.no_start)
    print('Provisioning complete. Verify the actual web, proxy, DNS, SSH and desktop paths before accepting the deployment.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('Native installation stopped: ' + str(error), file=sys.stderr)
        sys.exit(1)
