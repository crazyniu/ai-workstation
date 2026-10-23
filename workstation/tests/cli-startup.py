#!/usr/bin/env python3
"""Observe first-run desktop CLIs in real PTYs in a disposable clean container.

No login choices or prompts are submitted. Output stays in memory and only
recognized first-run UI markers are reported; no terminal transcript is saved.
"""
import fcntl
import json
import os
import pty
import select
import signal
import struct
import subprocess
import termios
import time


def observe(tool):
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 120, 0, 0))
    process = subprocess.Popen(
        ['/usr/bin/python3', '/etc/workstation/desktop-cli.py', tool],
        stdin=slave, stdout=slave, stderr=slave, start_new_session=True,
        env=dict(os.environ, TERM='xterm-256color'))
    os.close(slave)
    output = b''
    try:
        deadline = time.monotonic() + 18
        while time.monotonic() < deadline:
            if select.select([master], [], [], .25)[0]:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                output += chunk
                for query, response in [
                    (b'\x1b[6n', b'\x1b[1;1R'),
                    (b'\x1b]11;?', b'\x1b]11;rgb:0000/0000/0000\x1b\\'),
                    (b'\x1b[c', b'\x1b[?1;2c'),
                    (b'\x1b[?u', b'\x1b[?0u'),
                ]:
                    if query in chunk:
                        os.write(master, response)
            if process.poll() is not None:
                break
        text = output.decode(errors='replace').lower()
        markers = [word for word in ('welcome', 'sign in', 'log in', 'theme', 'openai', 'anthropic')
                   if word in text]
        errors = [word for word in ('econnreset', 'unable to connect', 'failed to connect', 'panic')
                  if word in text]
        result = {'tool': tool, 'alive_after_18_seconds': process.poll() is None,
                  'natural_exit': process.poll(), 'first_run_markers': markers,
                  'connection_error_markers': errors}
        print(json.dumps(result), flush=True)
        assert result['alive_after_18_seconds'] and markers and not errors, 'CLI first-run PTY failed'
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        os.close(master)


if __name__ == '__main__':
    assert os.getuid() != 0, 'Run only as the disposable desktop user'
    for name in ('codex', 'claude'):
        observe(name)
