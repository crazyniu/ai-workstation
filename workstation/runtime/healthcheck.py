import socket
import subprocess
from pathlib import Path
for port, expected in ((22, b'SSH-'), (5901, b'RFB ')):
    with socket.create_connection(('127.0.0.1', port), timeout=2) as connection:
        assert connection.recv(64).startswith(expected)
assert Path('/tmp/.X11-unix/X1').exists()
states = subprocess.check_output(['ps', '-u', '1100', '-o', 'comm=,stat='], text=True)
running = {name for name, state in (line.rsplit(None, 1) for line in states.splitlines())
           if not state.startswith('Z')}
for process in ('xfce4-session', 'xfwm4', 'xfdesktop', 'xfce4-panel'):
    assert process in running, process + ' is not running'
