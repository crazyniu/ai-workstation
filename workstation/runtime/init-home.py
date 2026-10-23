#!/usr/bin/python3
"""Populate user-owned state without granting user paths root privileges."""
import os
from pathlib import Path
import subprocess
import sys

assert os.getuid() == 1100, 'HOME initialization must run as dev'
os.umask(0o077)
home = Path('/home/dev')
password = sys.stdin.buffer.readline()
subprocess.run(['cp', '-an', '/opt/workstation/home-template/.', str(home)], check=True)
(home / 'Projects').mkdir(exist_ok=True)
subprocess.run(['python3', '/opt/workstation/scripts/configure-mcp.py', '--home', str(home)], check=True)
for relative in ('.codex/config.toml', '.claude.json'):
    (home / relative).chmod(0o600)
vnc = home / '.config/tigervnc'
vnc.mkdir(parents=True, exist_ok=True)
vnc.chmod(0o700)
encoded = subprocess.run(['tigervncpasswd', '-f'], input=password, stdout=subprocess.PIPE, check=True).stdout
target = vnc / 'passwd'
target.write_bytes(encoded)
target.chmod(0o600)
(home / '.workstation-home-initialized').touch(mode=0o600)
