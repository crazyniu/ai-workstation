#!/usr/bin/env python3
"""Opt-in, container-internal DoH resolver for a gateway's per-client upstream."""
import argparse
import configparser
import ctypes
import ctypes.util
import hashlib
import fnmatch
import io
import ipaddress
import json
import os
from pathlib import Path
import platform
import secrets
import shlex
import shutil
import socket
import subprocess
import tarfile
import time
import urllib.request

VERSION = 'v0.107.79'
URL = f'https://github.com/AdguardTeam/AdGuardHome/releases/download/{VERSION}/AdGuardHome_linux_amd64.tar.gz'
ARCHIVE_SHA256 = 'c48f4a43000665484c5ec28177de11a004759b620dae8f77b2aabefc9ef3687f'
BINARY_SHA256 = '7e247573e63ce771a5925d16ca4ca9344e6e888673244289dc302f0fdfdfbf4e'
if platform.machine() in ('aarch64', 'arm64'):
    URL = f'https://github.com/AdguardTeam/AdGuardHome/releases/download/{VERSION}/AdGuardHome_linux_arm64.tar.gz'
    ARCHIVE_SHA256 = '3f7893c18e8aaadc456d0452839190561c306ca95175a2254958be80a769c1ae'
    BINARY_SHA256 = '64a9b6fc6269247f1973cddbf285aa6ce866d11bd29546b0f4135ba31d2283c8'
PROGRAM = Path('/opt/workstation-exit-dns')
DATA = Path('/var/lib/workstation-exit-dns')
SERVICE = Path('/etc/supervisor/conf.d/workstation-exit-dns.conf')
SUPERVISOR = '/etc/supervisor/supervisord.conf'
if Path('/etc/systemd/system/ai-workstation.service').is_file():
    SUPERVISOR = '/etc/workstation/supervisord.conf'
    SERVICE = Path('/etc/workstation/conf.d/workstation-exit-dns.conf')


def addresses(source, gateway, port):
    source, gateway = ipaddress.IPv4Address(source), ipaddress.IPv4Address(gateway)
    if any(x.is_unspecified or x.is_multicast or x.is_loopback for x in (source, gateway)):
        raise ValueError('Use distinct, reachable LAN IPv4 addresses')
    if source == gateway or not 1024 <= port <= 65535:
        raise ValueError('Use distinct addresses and an unprivileged DNS port')
    return str(source), str(gateway)


def password_hash():
    # libxcrypt is supplied by the Linux password tools, including on Python 3.13+.
    library = ctypes.util.find_library('crypt')
    if not library:
        raise RuntimeError('libcrypt with BCrypt support is required')
    crypt = ctypes.CDLL(library).crypt
    crypt.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    crypt.restype = ctypes.c_char_p
    alphabet = './ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    salt = '$2b$12$' + ''.join(secrets.choice(alphabet) for _ in range(21)) + secrets.choice('.Oeu')
    result = crypt(secrets.token_urlsafe(48).encode(), salt.encode())
    if not result or len(result) != 60 or not result.startswith(b'$2b$12$'):
        raise RuntimeError('System libcrypt does not support BCrypt')
    return result.decode()


def configuration(source, gateway, port, hashed_password):
    source, gateway = addresses(source, gateway, port)
    return {
        'schema_version': 34,
        'http': {'address': '127.0.0.1:3001', 'pprof': {'enabled': False}},
        'users': [{'name': 'resolver-admin', 'password': hashed_password}],
        'language': 'en', 'http_proxy': '',
        'dns': {
            'bind_hosts': ['127.0.0.1', source], 'port': port,
            'allowed_clients': [gateway + '/32', '127.0.0.1/32'],
            'upstream_dns': ['https://1.1.1.1/dns-query', 'https://8.8.8.8/dns-query'],
            'bootstrap_dns': [], 'fallback_dns': [], 'upstream_mode': 'load_balance',
            'upstream_timeout': '5s', 'use_private_ptr_resolvers': False,
            'local_ptr_upstreams': [], 'hostsfile_enabled': False,
            'use_http3_upstreams': False, 'serve_http3': False,
            'edns_client_subnet': {'enabled': False, 'use_custom': False, 'custom_ip': ''},
            'cache_enabled': True, 'cache_size': 4194304, 'ratelimit': 100,
            'max_goroutines': 100, 'serve_plain_dns': True, 'handle_ddr': False,
        },
        'filtering': {'protection_enabled': False, 'filtering_enabled': False,
                      'parental_enabled': False, 'safebrowsing_enabled': False},
        'filters': [], 'whitelist_filters': [], 'user_rules': [],
        'querylog': {'enabled': False, 'file_enabled': False},
        'statistics': {'enabled': False}, 'dhcp': {'enabled': False},
        'tls': {'enabled': False},
    }


def verified_artifacts(archive):
    if hashlib.sha256(archive).hexdigest() != ARCHIVE_SHA256:
        raise ValueError('AdGuard release archive SHA256 mismatch')
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
        # Read named regular files only; never extract paths or symlinks.
        result = {}
        for name in ('AdGuardHome', 'LICENSE.txt'):
            matches = [m for m in tar.getmembers()
                       if m.name.removeprefix('./') == 'AdGuardHome/' + name]
            if len(matches) != 1:
                raise ValueError('Missing or duplicate AdGuard release member')
            member = matches[0]
            if not member.isfile() or member.size > 64 * 1024 * 1024:
                raise ValueError('Invalid AdGuard release member')
            result[name] = tar.extractfile(member).read()
    if hashlib.sha256(result['AdGuardHome']).hexdigest() != BINARY_SHA256:
        raise ValueError('AdGuard executable SHA256 mismatch')
    return result


def supervisor_configuration():
    return f'''[program:workstation-exit-dns]
command={PROGRAM}/AdGuardHome --no-check-update -c {DATA}/AdGuardHome.yaml -w {DATA}/work
user=nobody
environment=HTTP_PROXY="",HTTPS_PROXY="",ALL_PROXY="",http_proxy="",https_proxy="",all_proxy="",NO_PROXY="*",no_proxy="*"
priority=15
autostart=true
autorestart=true
startsecs=2
stopasgroup=true
killasgroup=true
stdout_logfile=/dev/fd/1
stdout_logfile_maxbytes=0
redirect_stderr=true
'''


def install(source, gateway, port):
    addresses(source, gateway, port)
    if os.getuid() != 0 or platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'aarch64', 'arm64'):
        raise ValueError('Apply inside the Linux amd64/arm64 workstation as root')
    if any(p.exists() or p.is_symlink() for p in (PROGRAM, DATA, SERVICE)):
        raise ValueError('Existing resolver files found; inspect or roll back before installing')
    settings = configparser.RawConfigParser()
    settings.read(SUPERVISOR)
    includes = shlex.split(settings.get('include', 'files', fallback=''))
    if not any(fnmatch.fnmatch(str(SERVICE), str(Path(SUPERVISOR).parent / p)) for p in includes):
        raise ValueError('Supervisor must include the selected resolver service directory; upgrade separately')
    subprocess.run(['supervisorctl', '-c', SUPERVISOR, 'pid'], check=True,
                   stdout=subprocess.DEVNULL)
    for host, candidate_port in ((source, port), ('127.0.0.1', port), ('127.0.0.1', 3001)):
        with socket.socket() as probe:
            probe.bind((host, candidate_port))
    config = configuration(source, gateway, port, password_hash())
    with urllib.request.urlopen(URL, timeout=120) as response:
        archive = response.read(64 * 1024 * 1024 + 1)
    if len(archive) > 64 * 1024 * 1024:
        raise ValueError('AdGuard release archive is too large')
    artifacts = verified_artifacts(archive)
    # All network/identity/port validation precedes the first persistent write.
    import pwd
    nobody = pwd.getpwnam('nobody')
    added = False
    try:
        PROGRAM.mkdir(mode=0o755)
        DATA.mkdir(mode=0o700)
        (DATA / 'work').mkdir(mode=0o700)
        for name, content in artifacts.items():
            path = PROGRAM / name
            path.write_bytes(content)
            path.chmod(0o755 if name == 'AdGuardHome' else 0o644)
        config_path = DATA / 'AdGuardHome.yaml'
        config_path.write_text(json.dumps(config, indent=2) + '\n')
        config_path.chmod(0o600)
        for path in (config_path, DATA / 'work', DATA):
            os.chown(path, nobody.pw_uid, nobody.pw_gid)
        subprocess.run([str(PROGRAM / 'AdGuardHome'), '--check-config', '--no-check-update',
                        '-c', str(config_path), '-w', str(DATA / 'work')], check=True)
        SERVICE.write_text(supervisor_configuration())
        SERVICE.chmod(0o600)
        subprocess.run(['supervisorctl', '-c', SUPERVISOR, 'reread'], check=True)
        added = True
        subprocess.run(['supervisorctl', '-c', SUPERVISOR, 'update', 'workstation-exit-dns'], check=True)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            status = subprocess.run(['supervisorctl', '-c', SUPERVISOR, 'status', 'workstation-exit-dns'],
                                    capture_output=True, text=True)
            if 'RUNNING' in status.stdout:
                break
            if any(s in status.stdout for s in ('FATAL', 'BACKOFF', 'EXITED')):
                raise RuntimeError('Resolver failed to start; inspect Supervisor logs')
            time.sleep(0.2)
        else:
            raise RuntimeError('Resolver startup timed out')
    except BaseException:
        # This installer refuses existing paths, so cleanup owns only these files.
        if added:
            subprocess.run(['supervisorctl', '-c', SUPERVISOR, 'stop', 'workstation-exit-dns'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        SERVICE.unlink(missing_ok=True)
        subprocess.run(['supervisorctl', '-c', SUPERVISOR, 'reread'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if added:
            subprocess.run(['supervisorctl', '-c', SUPERVISOR, 'update', 'workstation-exit-dns'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shutil.rmtree(DATA, ignore_errors=True)
        shutil.rmtree(PROGRAM, ignore_errors=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-ip', required=True)
    parser.add_argument('--gateway-ip', required=True)
    parser.add_argument('--port', type=int, default=5354)
    parser.add_argument('--apply', action='store_true', help='Install; default prints a credential-free plan')
    args = parser.parse_args()
    source, gateway = addresses(args.source_ip, args.gateway_ip, args.port)
    if args.apply:
        install(source, gateway, args.port)
        print('Dedicated resolver installed; now configure only this client on the gateway.')
    else:
        print(json.dumps({'source': source, 'allowed_gateway': gateway, 'port': args.port,
                          'version': VERSION, 'bootstrap': [], 'fallback': [],
                          'requires': 'An enforced, fixed proxy route for this source address'}))


if __name__ == '__main__':
    main()
