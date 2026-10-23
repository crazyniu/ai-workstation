import socket
import subprocess
from pathlib import Path
for port, expected in ((22, b'SSH-'), (5901, b'RFB ')):
    with socket.create_connection(('127.0.0.1', port), timeout=2) as connection:
        assert connection.recv(64).startswith(expected)
assert Path('/tmp/.X11-unix/X1').exists()
for process in ('xfce4-session', 'xfdesktop', 'xfce4-panel'):
    subprocess.run(['pgrep', '-u', '1100', '-x', process], check=True, stdout=subprocess.DEVNULL)
