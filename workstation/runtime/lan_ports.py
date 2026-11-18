"""Admin-approved, outbound LAN port exceptions for the optional workstation firewall."""
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import pwd
import socket
import struct
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

SOCKET = b'\0ai-workstation-lan-firewall'
STATE = Path('/etc/workstation/lan-ports.json')
CONTEXT = Path('/run/workstation-lan.json')
PROFILE = Path('/etc/profile.d/workstation-lan-ports.sh')


def atomic_write(path, text, mode=0o600):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        tmp = Path(stream.name)
        try:
            stream.write(text)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)


def rule(protocol, host, port):
    ip = ipaddress.IPv4Address(host)
    port = int(port)
    if protocol not in ('tcp', 'udp') or not 1 <= port <= 65535:
        raise ValueError('Choose TCP or UDP and a port from 1 to 65535.')
    return protocol, str(ip), port


def on_lan(entry, lan, gateway):
    ip = ipaddress.IPv4Address(entry[1])
    return (ip in lan and ip not in (gateway, lan.network_address, lan.broadcast_address)
            and not (ip.is_multicast or ip.is_loopback or ip.is_unspecified))


def peer_uid(connection):
    return struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]


def firewall_request(message):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(8)
        client.connect(SOCKET)
        if peer_uid(client) != 0:
            raise ValueError('The LAN firewall helper must run as root.')
        client.sendall(json.dumps(message).encode() + b'\n')
        client.shutdown(socket.SHUT_WR)
        with client.makefile('rb') as reply:
            line = reply.readline()
        if not line:
            raise ValueError('The firewall did not acknowledge the update. Check the helper image version.')
        result = json.loads(line)
        if result.get('ok') is not True:
            raise ValueError(result.get('error', 'The firewall rejected the rules.'))
        return result


def read_rules():
    if not STATE.exists():
        return []
    return [rule(*row) for row in json.loads(STATE.read_text())]


def save_rules(entries):
    atomic_write(STATE, json.dumps(entries, indent=2) + '\n')


def change(context, action, entry=None):
    # Serialize persistence and live updates from SSH, the desktop menu and startup.
    with open('/run/workstation-lan-ports.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        entries = read_rules()
        lan = ipaddress.IPv4Network(context['lan'], strict=False)
        gateway = ipaddress.IPv4Address(context['gateway'])
        if action == 'seed':
            action = 'sync' if STATE.exists() else 'add'
        if action == 'add':
            if not on_lan(entry, lan, gateway):
                raise ValueError(f'Choose a device on {lan}. Gateway service access is managed on the gateway.')
            if entry not in entries:
                entries.append(entry)
        elif action == 'remove':
            entries = [row for row in entries if row != entry]
        if action in ('add', 'remove'):
            save_rules(entries)
        allowed = [row for row in entries if on_lan(row, lan, gateway)]
        hosts = sorted({row[1] for row in allowed}) if context['isolated'] else []
        if context['isolated']:
            try:
                firewall_request(allowed)
            except (ValueError, OSError) as exc:
                raise ValueError(f'Saved rules are not confirmed active. Choose Reapply to retry. {exc}') from exc
        # Exact IPv4 addresses also work in proxy clients without NO_PROXY CIDR support.
        script = ''
        if hosts:
            script = """no_proxy=${no_proxy-${NO_PROXY-}}
for _ws_peer in %s; do
  case ",${NO_PROXY-}," in *",$_ws_peer,"*) ;; *) NO_PROXY="${NO_PROXY:+$NO_PROXY,}$_ws_peer" ;; esac
  case ",${no_proxy-}," in *",$_ws_peer,"*) ;; *) no_proxy="${no_proxy:+$no_proxy,}$_ws_peer" ;; esac
done
unset _ws_peer
export NO_PROXY no_proxy
""" % ' '.join(hosts)
        atomic_write(PROFILE, script, 0o644)
        return hosts


def initialize():
    isolated = os.environ.get('WORKSTATION_LAN_GUARD') == 'required'
    if isolated:
        network = firewall_request('network')
        context = {'lan': network['lan'], 'gateway': network['gateway'], 'isolated': True}
    else:
        context = {'lan': os.environ['WORKSTATION_LAN'], 'gateway': os.environ['WORKSTATION_GATEWAY'], 'isolated': False}
    atomic_write(CONTEXT, json.dumps(context))
    seed = os.environ.get('WORKSTATION_INITIAL_ORCA_ENDPOINT', '').strip()
    initial = None
    if seed and not STATE.exists():
        try:
            host, port = seed.rsplit(':', 1)
            initial = rule('tcp', host, port)
            if not on_lan(initial, ipaddress.IPv4Network(context['lan'], strict=False), ipaddress.IPv4Address(context['gateway'])):
                raise ValueError('The address is not a peer on the workstation LAN.')
        except ValueError:
            print('Initial Orca endpoint skipped. Use an on-LAN IPv4:port or niu.sh option 7.', file=sys.stderr)
            initial = None
    hosts = change(context, 'seed' if initial else 'sync', initial)
    print(','.join(hosts))


def paired_endpoints():
    path = Path(pwd.getpwuid(os.getuid()).pw_dir) / '.orca/orca-environments.json'
    items = []
    if path.is_file():
        for env in json.loads(path.read_text()).get('environments', []):
            for endpoint in env.get('endpoints', []):
                if endpoint.get('kind') != 'websocket':
                    continue
                try:
                    url = urlsplit(endpoint['endpoint'])
                    if url.scheme not in ('ws', 'wss'):
                        continue
                    port = url.port if url.port is not None else (443 if url.scheme == 'wss' else 80)
                    row = rule('tcp', url.hostname, port)
                except (TypeError, ValueError):
                    continue
                if row not in items:
                    items.append(row)
    # Output only network destinations, never the pairing URL, path or device token.
    print(json.dumps(items))


def choose(entries):
    for index, (protocol, host, port) in enumerate(entries, 1):
        print(f'  {index}. {host}:{port}/{protocol}')
    if not entries:
        print('No entries.')
        return None
    value = input('Number (0 = back): ').strip()
    if value == '0':
        return None
    if not value.isdigit() or not 1 <= int(value) <= len(entries):
        raise ValueError('Choose a number from the list.')
    return entries[int(value) - 1]


def menu():
    if not CONTEXT.is_file():
        raise ValueError('LAN port rules require a workstation deployed with the Linux LAN template.')
    context = json.loads(CONTEXT.read_text())
    lan = ipaddress.IPv4Network(context['lan'], strict=False)
    gateway = ipaddress.IPv4Address(context['gateway'])
    while True:
        entries = read_rules()
        print('\nLAN isolation:', 'enabled' if context['isolated'] else 'off (rules saved for later)')
        print('Saved outbound ports:')
        for protocol, host, port in entries:
            suffix = '' if on_lan((protocol, host, port), lan, gateway) else ' (outside current LAN policy)'
            print(f'  {host}:{port}/{protocol}{suffix}')
        if not entries:
            print('  None')
        print('1. Allow a paired Orca endpoint\n2. Allow a device port\n3. Remove a rule\n4. Reapply saved rules\n0. Back')
        choice = input('Choose a number: ').strip()
        try:
            if choice == '0':
                return
            if choice == '1':
                # Pairing data belongs to dev; never follow a user path with root privileges.
                raw = subprocess.check_output(['runuser', '-u', 'dev', '--', sys.executable, '-I',
                                               __file__, 'paired'])
                peers = [rule(*e) for e in json.loads(raw) if on_lan(e, lan, gateway)]
                if not peers:
                    print('No paired Orca endpoint has an IPv4 on this LAN. Use option 2 for a known device port.')
                    continue
                row = choose(peers)
            elif choice == '2':
                host = input('Destination IPv4: ').strip()
                port = input('Destination port: ').strip()
                protocol = input('Protocol [tcp/udp, default tcp]: ').strip().lower() or 'tcp'
                row = rule(protocol, host, port)
            elif choice == '3':
                row = choose(entries)
            elif choice == '4':
                if input('Reapply saved rules?  1. Confirm  0. Cancel: ').strip() != '1':
                    continue
                change(context, 'sync')
                print('Applied.' if context['isolated'] else 'Saved for isolation mode.')
                continue
            else:
                continue
            if row is not None:
                protocol, host, port = row
                operation = 'Remove' if choice == '3' else 'Allow'
                if input(f'{operation} {host}:{port}/{protocol}?  1. Confirm  0. Cancel: ').strip() != '1':
                    continue
                change(context, 'remove' if choice == '3' else 'add', row)
                print('Saved and applied.' if context['isolated'] else 'Saved for isolation mode.')
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            print(str(exc), file=sys.stderr)


if __name__ == '__main__':
    try:
        if sys.argv[1:] == ['paired']:
            paired_endpoints()
        elif os.getuid() != 0:
            sys.exit('Administrator access is required.')
        elif sys.argv[1:] == ['init']:
            initialize()
        elif sys.argv[1:] == ['menu']:
            menu()
        else:
            sys.exit('Choose menu or init.')
    except (ValueError, OSError) as error:
        sys.exit(str(error))
    except (KeyboardInterrupt, EOFError):
        print()
