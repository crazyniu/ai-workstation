#!/usr/bin/python3
"""Initialize persistent user state and runtime-only credentials, then start services."""
import json
import os
from pathlib import Path
import subprocess
import sys

def secret(name, required=False, default=''):
    filename = os.environ.get(name + '_FILE')
    value = Path(filename).read_text().rstrip('\r\n') if filename else os.environ.get(name, default)
    if required and not value:
        raise ValueError(name + '_FILE is required; no password is included in the image')
    if any(char in value for char in '\r\n\x00:'):
        raise ValueError(name + ' contains unsupported characters')
    return value

def initialize_passwords(native, root=Path('/')):
    # Root-owned state, independent of the editable HOME initialization marker.
    marker = root / 'etc/workstation/credentials-initialized'
    if marker.exists():
        return
    shadow = dict(line.split(':', 2)[:2] for line in
                  (root / 'etc/shadow').read_text().splitlines())
    credentials = []
    # Preserve existing hashes, including locked hashes, when upgrading an older image.
    if shadow['dev'].lstrip('!') in ('', '*'):
        credentials.append('dev:' + secret('DEV_PASSWORD', required=True,
                                          default='' if native else 'dev'))
    if not native and shadow['root'].lstrip('!') in ('', '*'):
        password = secret('ROOT_PASSWORD', default='root')
        if password:
            credentials.append('root:' + password)
        else:
            subprocess.run(['usermod', '--lock', 'root'], check=True)
    if credentials:
        subprocess.run(['chpasswd'], input=('\n'.join(credentials)+'\n').encode(), check=True)
    marker.touch(mode=0o600)


def main():
    if os.getuid() != 0:
        raise ValueError('The entrypoint needs root to start SSH; applications run as dev')
    native = os.environ.get('WORKSTATION_INSTALL_MODE') == 'native'
    if not native and (os.environ.get('WORKSTATION_LAN') or os.environ.get('WORKSTATION_LAN_GUARD') == 'required'):
        hosts = subprocess.check_output(['python3', '-I', '/etc/workstation/lan_ports.py', 'init'], text=True).strip()
        if hosts:
            upper = os.environ.get('NO_PROXY', '')
            lower = os.environ.get('no_proxy', upper)
            for key, previous in [('NO_PROXY', upper), ('no_proxy', lower)]:
                os.environ[key] = ','.join(dict.fromkeys(filter(None, [*previous.split(','), *hosts.split(',')])))
    vnc_auth = os.environ.get('VNC_AUTH', 'password')
    if vnc_auth not in ('password', 'none'):
        raise ValueError('VNC_AUTH must be password or none')
    vnc_password = ''
    if vnc_auth == 'password' and not Path('/home/dev/.config/tigervnc/passwd').exists():
        vnc_password = secret('VNC_PASSWORD', required=True)
    if vnc_password and not 1 <= len(vnc_password.encode('ascii')) <= 8:
        raise ValueError('VNC password must be 1–8 ASCII bytes for Mac Screen Sharing')
    # Apply region to system/PAM configuration and every supervised child.
    # Fail before touching user state if a requested locale/timezone is invalid.
    region = subprocess.check_output(['python3', '/etc/workstation/region.py'], text=True)
    os.environ.update(json.loads(region))
    home = Path('/home/dev')
    if home.is_symlink():
        raise ValueError('/home/dev must be a real directory')
    home.mkdir(parents=True, exist_ok=True)
    os.chown(home, 1100, 1100)
    home.chmod(0o700)
    if not native:
        subprocess.run(['python3', '/etc/workstation/desktop-permissions.py'], check=True)
    initialize_passwords(native)
    for name in ('DEV_PASSWORD', 'ROOT_PASSWORD', 'VNC_PASSWORD', 'GATEWAY_CONTAINER_PASSWORD', 'GATEWAY_ADMIN_PASSWORD'):
        os.environ.pop(name, None)
    child_env = dict(os.environ, HOME=str(home), USER='dev', LOGNAME='dev')
    subprocess.run(['runuser', '-u', 'dev', '--', 'python3', '/etc/workstation/init-home.py'],
                   input=(vnc_password+'\n').encode(), env=child_env, check=True)
    keys = Path('/etc/workstation/ssh-keys' if native else '/etc/ssh/keys')
    keys.mkdir(parents=True, exist_ok=True)
    keys.chmod(0o700)
    key = keys / 'ssh_host_ed25519_key'
    if not key.exists():
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
    Path('/run/sshd').mkdir(parents=True, exist_ok=True)
    config = '/etc/workstation/supervisord.conf' if native else '/etc/supervisor/supervisord.conf'
    os.execv('/usr/bin/supervisord', ['supervisord', '-n', '-c', config])

if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('Workstation initialization failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
