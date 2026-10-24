#!/usr/bin/env python3
"""Real HTTPS/WebSocket/RFB acceptance, including password-free mode and origins."""
import argparse
import base64
import hashlib
import os
from pathlib import Path
import socket
import ssl
import struct
import subprocess
import urllib.request


def upgrade(host, origin, scheme='https'):
    sock = socket.create_connection((host, 6080), timeout=5)
    if scheme == 'https':
        sock = ssl._create_unverified_context().wrap_socket(sock, server_hostname=host)
    key = base64.b64encode(os.urandom(16)).decode()
    headers = [f'GET /websockify HTTP/1.1', f'Host: {host}:6080',
               'Upgrade: websocket', 'Connection: Upgrade',
               'Sec-WebSocket-Version: 13', 'Sec-WebSocket-Key: ' + key,
               'Sec-WebSocket-Protocol: binary']
    if origin is not None:
        headers.append('Origin: ' + origin)
    sock.sendall(('\r\n'.join(headers) + '\r\n\r\n').encode())
    stream = sock.makefile('rb')
    status = stream.readline().decode().strip()
    response = {}
    while True:
        line = stream.readline()
        if line == b'\r\n':
            break
        assert line and len(line) < 8192
        k, v = line.decode().split(':', 1)
        response[k.lower()] = v.strip()
    if ' 101 ' in status:
        expected = base64.b64encode(hashlib.sha1(
            (key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
        assert response.get('sec-websocket-accept') == expected
    return sock, stream, status


class Transport:
    def __init__(self, sock, stream):
        self.sock, self.stream, self.buffer = sock, stream, bytearray()

    def send(self, payload):
        mask = os.urandom(4)
        assert len(payload) < 126
        self.sock.sendall(bytes([0x82, 0x80 | len(payload)]) + mask +
                          bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def read(self, size):
        while len(self.buffer) < size:
            header = self.stream.read(2)
            assert len(header) == 2 and header[0] & 0xf in (0, 2), 'Expected RFB data frame'
            assert not header[1] & 0x80, 'Server frames must not be masked'
            length = header[1] & 0x7f
            if length == 126:
                length = struct.unpack('>H', self.stream.read(2))[0]
            elif length == 127:
                length = struct.unpack('>Q', self.stream.read(8))[0]
            assert length < 16 * 1024 * 1024
            payload = self.stream.read(length)
            assert len(payload) == length
            self.buffer.extend(payload)
        data = bytes(self.buffer[:size])
        del self.buffer[:size]
        return data


def check(host, auth, scheme='https'):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
    with opener.open(f'{scheme}://{host}:6080/', timeout=5) as response:
        assert b'autoconnect=1' in response.read()
    with opener.open(f'{scheme}://{host}:6080/vnc.html', timeout=5) as response:
        assert b'noVNC' in response.read()
    for origin in ('https://unrelated.invalid', None):
        sock, stream, status = upgrade(host, origin, scheme)
        try:
            assert ' 403 ' in status, status
        finally:
            stream.close(); sock.close()
    sock, stream, status = upgrade(host, f'{scheme}://{host}:6080', scheme)
    try:
        assert ' 101 ' in status, status
        ws = Transport(sock, stream)
        assert ws.read(12) == b'RFB 003.008\n'
        ws.send(b'RFB 003.008\n')
        methods = ws.read(ws.read(1)[0])
        if auth == 'none':
            assert methods == b'\x01', methods
            ws.send(b'\x01')
        else:
            assert methods == b'\x02', methods
            ws.send(b'\x02')
            filename = os.environ.get('VNC_PASSWORD_FILE')
            password = (Path(filename).read_text().rstrip('\r\n') if filename
                        else os.environ['VNC_PASSWORD']).encode('ascii')
            key = bytes(int(f'{b:08b}'[::-1], 2) for b in password.ljust(8, b'\0'))
            result = subprocess.run(['node', '--openssl-legacy-provider', '-e', '''
const crypto = require('node:crypto');
const input = require('node:fs').readFileSync(0);
const cipher = crypto.createCipheriv('des-ecb', input.subarray(0, 8), null);
cipher.setAutoPadding(false);
process.stdout.write(Buffer.concat([cipher.update(input.subarray(8)), cipher.final()]));
'''], input=key + ws.read(16), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=10, check=True)
            ws.send(result.stdout)
        assert ws.read(4) == b'\0\0\0\0', 'RFB authentication failed'
        ws.send(b'\x01')
        init = ws.read(24)
        width, height = struct.unpack('>HH', init[:4])
        length = struct.unpack('>I', init[20:])[0]
        assert width > 0 and height > 0 and 0 < length < 4096
        ws.read(length)
    finally:
        stream.close(); sock.close()
    print('PASS: ' + scheme.upper() + ', noVNC page, origin rejection and full RFB handshake; auth=' + auth)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--auth', choices=['none', 'password'], default='password')
    parser.add_argument('--scheme', choices=['http', 'https'], default='https')
    args = parser.parse_args()
    check(args.host, args.auth, args.scheme)
