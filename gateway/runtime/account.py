#!/usr/bin/env python3
"""Keep SSH identity and the administrator's shell account in the data volume."""
import os
import ipaddress
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, '/opt/gateway/app')
from state import ROOT, atomic, read, save

account = ROOT / 'system/account.json'
value = read(account)
name = os.environ.get('GATEWAY_CONTAINER_USER') or (value or {}).get('name', 'root')
password = os.environ.get('GATEWAY_CONTAINER_PASSWORD')
if value is None and password is None:
    password = 'root'
if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,30}', name):
    raise ValueError('GATEWAY_CONTAINER_USER must name a valid Linux account')
if password is not None and (not password or any(c in password for c in '\r\n\x00:')):
    raise ValueError('GATEWAY_CONTAINER_PASSWORD is invalid')
native = os.environ.get('GATEWAY_INSTALL_MODE') == 'native'
exists = subprocess.run(['id', '-u', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
if native and exists and name != 'root' and (not value or value.get('name') != name):
    raise ValueError('Existing host account cannot be used as a new gateway administrator')
if not exists:
    subprocess.run(['useradd', '-M', '-d', str(ROOT / 'home'), '-s', '/bin/bash', name], check=True)
if not value or value.get('name') != name:
    value = {'name': name}
home = ROOT / 'home'
home.mkdir(exist_ok=True)
import pwd
user = pwd.getpwnam(name)
os.chown(home, user.pw_uid, user.pw_gid)
home.chmod(0o700)
if native and name == 'root':
    # SSH uses the host's own account database. Keep the host hash out of gateway backups.
    if read(account) != {'name': name}:
        save(account, {'name': name})
elif password is not None:
    subprocess.run(['chpasswd'], input=f'{name}:{password}\n', text=True, check=True)
    value['hash'] = next(line.split(':')[1] for line in Path('/etc/shadow').read_text().splitlines() if line.startswith(name + ':'))
    save(account, value)
else:
    subprocess.run(['chpasswd', '-e'], input=f"{name}:{value['hash']}\n", text=True, check=True)
keys = ROOT / 'system/ssh'
keys.mkdir(parents=True, exist_ok=True)
keys.chmod(0o700)
key = keys / 'ssh_host_ed25519_key'
if not key.exists():
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
Path('/run/sshd').mkdir(exist_ok=True)
port = int(os.environ.get('GATEWAY_SSH_PORT', '22'))
bind = str(ipaddress.IPv4Address(os.environ.get('GATEWAY_BIND_ADDRESS', '0.0.0.0')))
if not 1 <= port <= 65535:
    raise ValueError('Invalid GATEWAY_SSH_PORT')
atomic('/run/gateway/sshd_config', f'''Port {port}
ListenAddress {bind}
HostKey {key}
PermitRootLogin {"yes" if name == "root" else "no"}
PasswordAuthentication yes
KbdInteractiveAuthentication no
UsePAM yes
AllowUsers {name}
Subsystem sftp internal-sftp
''')
