#!/usr/bin/env python3
"""Exercise runtime SSH and VNC passwords inside the isolated smoke container."""
import os
from pathlib import Path
import shlex
import socket
import struct
import subprocess
import tempfile


def receive(connection, length):
    result = b''
    while len(result) < length:
        block = connection.recv(length - len(result))
        if not block:
            raise AssertionError('VNC server closed the authentication connection')
        result += block
    return result


def runtime_secret(name):
    filename = os.environ.get(name + '_FILE')
    value = Path(filename).read_text().rstrip('\r\n') if filename else os.environ.get(name, '')
    if not value:
        raise ValueError(name + ' or ' + name + '_FILE must be set for the authentication test')
    return value


def ssh_login():
    password = runtime_secret('DEV_PASSWORD')
    with tempfile.TemporaryDirectory(prefix='workstation-ssh-auth-') as folder:
        askpass = Path(folder) / 'askpass'
        askpass.write_text('#!/bin/sh\nprintf \'%s\\n\' "$WORKSTATION_TEST_SSH_PASSWORD"\n')
        askpass.chmod(0o700)
        check = ('import os,pathlib; assert os.getuid()==1100 and os.getgid()==1100; '
                 's=pathlib.Path("/proc/self/status").read_text(); '
                 'assert "NoNewPrivs:\\t1" in s; print("WORKSTATION_SSH_AUTH_PASS")')
        result = subprocess.run([
            'ssh', '-T', '-o', 'BatchMode=no', '-o', 'NumberOfPasswordPrompts=1',
            '-o', 'PreferredAuthentications=password', '-o', 'PubkeyAuthentication=no',
            '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null',
            '-o', 'ConnectTimeout=5', 'dev@127.0.0.1',
            'python3 -c ' + shlex.quote(check),
        ], env=dict(os.environ, DISPLAY=':1', SSH_ASKPASS_REQUIRE='force', SSH_ASKPASS=str(askpass),
                    WORKSTATION_TEST_SSH_PASSWORD=password),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=20, start_new_session=True, check=True)
        assert result.stdout.strip() == b'WORKSTATION_SSH_AUTH_PASS'


def vnc_login(password):
    with socket.create_connection(('127.0.0.1', 5901), timeout=5) as connection:
        assert receive(connection, 12) == b'RFB 003.008\n'
        connection.sendall(b'RFB 003.008\n')
        count = receive(connection, 1)[0]
        assert count, 'VNC server rejected protocol negotiation'
        methods = receive(connection, count)
        assert methods == b'\x02', 'VNC must require VncAuth and must not offer unauthenticated access'
        connection.sendall(b'\x02')
        challenge = receive(connection, 16)
        # VNC DES uses reversed password bits. Node is already part of the image;
        # its legacy provider exposes DES solely for this protocol acceptance test.
        key = bytes(int(f'{byte:08b}'[::-1], 2) for byte in password.ljust(8, b'\0'))
        response = subprocess.run(['node', '--openssl-legacy-provider', '-e', '''
const crypto = require('node:crypto');
const input = require('node:fs').readFileSync(0);
const cipher = crypto.createCipheriv('des-ecb', input.subarray(0, 8), null);
cipher.setAutoPadding(false);
process.stdout.write(Buffer.concat([cipher.update(input.subarray(8)), cipher.final()]));
'''], input=key + challenge, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=True).stdout
        connection.sendall(response)
        return struct.unpack('>I', receive(connection, 4))[0]


if __name__ == '__main__':
    ssh_login()
    password = runtime_secret('VNC_PASSWORD').encode('ascii')
    assert vnc_login(password) == 0, 'VNC runtime password authentication failed'
    wrong_password = bytes([password[0] ^ 1]) + password[1:]
    assert vnc_login(wrong_password) != 0, 'VNC accepted an incorrect password'
    print('PASS: SSH password login runs as dev without new privileges; VNC accepts the configured password and rejects an incorrect one.')
