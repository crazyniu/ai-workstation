#!/usr/bin/python3
"""Window and failure acceptance inside disposable smoke containers only."""
import os
from pathlib import Path
import re
import signal
import subprocess
import time


def pids(name):
    result = subprocess.run(['pgrep', '-u', str(os.getuid()), '-x', name],
                            text=True, capture_output=True, timeout=5)
    found = []
    for pid in result.stdout.split():
        try:
            state = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0]
            if state != 'Z':
                found.append(int(pid))
        except FileNotFoundError:
            pass
    return found


def frame_is_visible(env):
    result = subprocess.run(['xprop', '-name', 'desktop-recovery-smoke',
                             '_NET_FRAME_EXTENTS'], env=env, text=True,
                            capture_output=True, timeout=5)
    match = re.search(r'=\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)', result.stdout)
    return match is not None and int(match[3]) > 0


assert os.getuid() == 1100, 'Run as the desktop user in a disposable container'
session, = pids('xfce4-session')
env = dict(item.decode().split('=', 1) for item in
           Path(f'/proc/{session}/environ').read_bytes().split(b'\0') if b'=' in item)
env = {**os.environ, **env}
query = ['xfconf-query', '-c', 'xfwm4', '-p']
for prop in ('titleless_maximize', 'borderless_maximize', 'use_compositing'):
    assert subprocess.check_output(query + ['/general/' + prop], env=env,
                                   text=True, timeout=5).strip() == 'false', prop
assert subprocess.check_output(['xfconf-query', '-c', 'xfce4-panel', '-p',
                                '/panels/panel-1/autohide-behavior'], env=env,
                               text=True, timeout=5).strip() == '0'

window = subprocess.Popen(['xfce4-terminal', '--disable-server',
                           '--title=desktop-recovery-smoke', '-x', 'sleep', '90'],
                          env=env, start_new_session=True)
try:
    deadline = time.monotonic() + 15
    while not frame_is_visible(env):
        assert window.poll() is None, 'Terminal exited before its frame appeared'
        assert time.monotonic() < deadline, 'New terminal has no title-bar extents'
        time.sleep(.2)
    before = {name: pids(name) for name in ('xfwm4', 'xfce4-panel')}
    assert all(len(found) == 1 for found in before.values()), before
    # Pause native session recovery to prove the independent guard repairs both.
    os.kill(session, signal.SIGSTOP)
    try:
        started = time.monotonic()
        for found in before.values():
            os.kill(found[0], signal.SIGKILL)
        deadline = started + 25
        while True:
            after = {name: pids(name) for name in before}
            if all(len(after[name]) == 1 and after[name] != before[name]
                   for name in before) and frame_is_visible(env):
                break
            assert time.monotonic() < deadline, f'Desktop did not recover: {after}'
            time.sleep(.2)
        print(f'PASS: independent guard restored panel and title bar in '
              f'{time.monotonic() - started:.2f}s; the terminal remained open.')
    finally:
        os.kill(session, signal.SIGCONT)
    time.sleep(3)
    assert window.poll() is None, 'Recovery closed the application'
    assert all(len(pids(name)) == 1 for name in before), 'Duplicate desktop components'
    subprocess.run(['python3', '/etc/workstation/healthcheck.py'], check=True, timeout=5)
finally:
    if window.poll() is None:
        os.killpg(window.pid, signal.SIGTERM)
    window.wait(timeout=5)
