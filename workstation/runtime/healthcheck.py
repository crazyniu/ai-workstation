import os
import socket
import subprocess
import ssl
import urllib.request
from pathlib import Path
with socket.create_connection(('127.0.0.1', int(os.environ.get('WORKSTATION_SSH_PORT', '22'))), timeout=2) as connection:
    assert connection.recv(64).startswith(b'SSH-')
# Opening and abandoning VNC authentication increments TigerVNC's blacklist.
# Inspect its listener without consuming authentication attempts.
assert subprocess.check_output(['ss', '-H', '-ltn', 'sport = :5901'], text=True).strip(), 'VNC is not listening'
assert Path('/tmp/.X11-unix/X1').exists()
states = subprocess.check_output(['ps', '-u', '1100', '-o', 'comm=,stat='], text=True)
running = {name for name, state in (line.rsplit(None, 1) for line in states.splitlines())
           if not state.startswith('Z')}
for process in ('Xtigervnc', 'xfce4-session', 'xfwm4', 'xfdesktop', 'xfce4-panel'):
    assert process in running, process + ' is not running'

# Read only the web page; health probes never initiate VNC authentication.
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
    urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
scheme = 'http' if os.environ.get('NOVNC_TLS', '1') == '0' else 'https'
with opener.open(scheme + '://127.0.0.1:6080/vnc.html', timeout=2) as response:
    assert response.status == 200
