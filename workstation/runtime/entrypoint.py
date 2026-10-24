#!/usr/bin/python3
"""Initialize persistent user state and runtime-only credentials, then start services."""
import json
import os
from pathlib import Path
import subprocess
import sys

def secret(name, required=False):
    filename = os.environ.get(name + '_FILE')
    value = Path(filename).read_text().rstrip('\r\n') if filename else os.environ.get(name, '')
    if required and not value:
        raise ValueError(name + '_FILE is required; no password is included in the image')
    if any(char in value for char in '\r\n\x00:'):
        raise ValueError(name + ' contains unsupported characters')
    return value

def main():
    if os.getuid() != 0:
        raise ValueError('The entrypoint needs root to start SSH; applications run as dev')
    dev_password = secret('DEV_PASSWORD', True)
    vnc_password = secret('VNC_PASSWORD', True)
    root_password = secret('ROOT_PASSWORD')
    if not 1 <= len(vnc_password.encode('ascii')) <= 8:
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
    for name in ('DEV_PASSWORD', 'ROOT_PASSWORD', 'VNC_PASSWORD'):
        os.environ.pop(name, None)
    child_env = dict(os.environ, HOME=str(home), USER='dev', LOGNAME='dev')
    subprocess.run(['runuser', '-u', 'dev', '--', 'python3', '/etc/workstation/init-home.py'],
                   input=(vnc_password+'\n').encode(), env=child_env, check=True)
    credentials = 'dev:' + dev_password + '\n'
    if root_password:
        credentials += 'root:' + root_password + '\n'
    else:
        subprocess.run(['usermod', '--lock', 'root'], check=True)
    subprocess.run(['chpasswd'], input=credentials.encode(), check=True)
    keys = Path('/etc/ssh/keys')
    keys.mkdir(parents=True, exist_ok=True)
    keys.chmod(0o700)
    key = keys / 'ssh_host_ed25519_key'
    if not key.exists():
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
    Path('/run/sshd').mkdir(parents=True, exist_ok=True)
    for name in ('DEV_PASSWORD', 'ROOT_PASSWORD', 'VNC_PASSWORD'):
        os.environ.pop(name, None)
    os.execv('/usr/bin/supervisord', ['supervisord', '-n', '-c', '/etc/supervisor/supervisord.conf'])

if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('Workstation initialization failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
