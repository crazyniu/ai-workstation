#!/usr/bin/env python3
"""Keep SSH identity and the administrator's shell account in the data volume."""
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, '/opt/gateway/app')
from state import ROOT, atomic, read, save

account = ROOT / 'system/account.json'
value = read(account)
name = os.environ.get('GATEWAY_CONTAINER_USER') or (value or {}).get('name', 'admin')
password = os.environ.get('GATEWAY_CONTAINER_PASSWORD')
if value is None and password is None:
    password = 'admin'
if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,30}', name) or name == 'root':
    raise ValueError('GATEWAY_CONTAINER_USER must name a non-root account')
if password is not None and (not password or any(c in password for c in '\r\n\x00:')):
    raise ValueError('GATEWAY_CONTAINER_PASSWORD is invalid')
if not value or value['name'] != name:
    value = {'name': name}
if subprocess.run(['id', '-u', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
    subprocess.run(['useradd', '-M', '-d', str(ROOT / 'home'), '-s', '/bin/bash', name], check=True)
home = ROOT / 'home'
home.mkdir(exist_ok=True)
import pwd
user = pwd.getpwnam(name)
os.chown(home, user.pw_uid, user.pw_gid)
home.chmod(0o700)
if password is not None:
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
atomic('/run/gateway/sshd_config', f'''Port 22
HostKey {key}
PermitRootLogin no
PasswordAuthentication yes
KbdInteractiveAuthentication no
UsePAM yes
AllowUsers {name}
Subsystem sftp internal-sftp
''')
for variable in ('GATEWAY_CONTAINER_PASSWORD', 'GATEWAY_ADMIN_PASSWORD'):
    os.environ.pop(variable, None)
