#!/usr/bin/python3
"""Restore missing XFCE window manager and panel in the active X11 session."""
import os
from pathlib import Path
import subprocess
import time


def processes(proc=Path('/proc')):
    result = {}
    display = os.environ.get('DISPLAY', ':1')
    for path in proc.iterdir():
        if not path.name.isdigit():
            continue
        try:
            if path.stat().st_uid != os.getuid():
                continue
            name = (path / 'comm').read_text().strip()
            if name not in ('xfce4-session', 'xfwm4', 'xfce4-panel'):
                continue
            env = dict(item.decode().split('=', 1) for item in
                       (path / 'environ').read_bytes().split(b'\0') if b'=' in item)
            if env.get('DISPLAY') == display:
                result.setdefault(name, []).append((int(path.name), env))
        except (OSError, ValueError, UnicodeError):
            continue
    return result


def main():
    session_pid = None
    ready_at = 0
    attempts = {}
    children = []
    while True:
        children = [child for child in children if child.poll() is None]
        current = processes()
        sessions = current.get('xfce4-session', [])
        now = time.monotonic()
        if not sessions:
            session_pid = None
        else:
            pid, session_env = max(sessions)
            if pid != session_pid:
                session_pid, ready_at = pid, now + 5
                attempts.clear()
            env = {**os.environ, **session_env}
            if Path(f'/tmp/.ICE-unix/{pid}').exists():
                hostname = os.uname().nodename
                env['SESSION_MANAGER'] = (
                    f'local/{hostname}:@/tmp/.ICE-unix/{pid},'
                    f'unix/{hostname}:/tmp/.ICE-unix/{pid}')
            if now >= ready_at:
                for name, command in [('xfwm4', ['xfwm4', '--compositor=off']),
                                      ('xfce4-panel', ['xfce4-panel'])]:
                    if name in current or now - attempts.get(name, -30) < 10:
                        continue
                    attempts[name] = now
                    print(f'Restoring {name} in XFCE session {pid}', flush=True)
                    try:
                        children.append(subprocess.Popen(command, env=env,
                                                          stdin=subprocess.DEVNULL))
                    except OSError as error:
                        print(f'Cannot start {name}: {error}', flush=True)
        time.sleep(2)


if __name__ == '__main__':
    main()
