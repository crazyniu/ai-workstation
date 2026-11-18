#!/usr/bin/python3
"""Own the workstation LAN namespace; desktop processes never receive NET_ADMIN."""
import ipaddress
import json
import os
import socket
import subprocess
import sys

from lan_ports import SOCKET, on_lan, peer_uid, rule


def ready():
    with socket.socket(socket.AF_UNIX) as client:
        client.connect(SOCKET)
        if peer_uid(client) != 0:
            raise ValueError('Invalid LAN firewall helper identity')


def update_ports(message, lan, gateway):
    entries = {rule(*row) for row in message}
    if not all(on_lan(entry, lan, gateway) for entry in entries):
        raise ValueError(f'Destinations must be unicast peers on {lan}.')
    commands = []
    for protocol in ('tcp', 'udp'):
        name = 'allow_' + protocol
        commands.append(f'flush set inet workstation {name}')
        values = [f'{ip} . {port}' for proto, ip, port in sorted(entries) if proto == protocol]
        if values:
            commands.append(f"add element inet workstation {name} {{ {', '.join(values)} }}")
    subprocess.run(['nft', '-f', '-'], input='\n'.join(commands)+'\n', text=True, check=True)


def handle_request(connection, lan, gateway):
    if peer_uid(connection) != 0:
        return
    connection.settimeout(3)
    with connection.makefile('rb') as stream:
        message = stream.readline()
    if not message:  # The readiness probe connects and closes.
        return
    try:
        request = json.loads(message)
        if request == 'network':
            result = {'ok': True, 'lan': str(lan), 'gateway': str(gateway)}
        else:
            update_ports(request, lan, gateway)
            result = {'ok': True}
    except (TypeError, ValueError, subprocess.CalledProcessError) as error:
        result = {'ok': False, 'error': str(error)}
    connection.sendall(json.dumps(result).encode() + b'\n')


def serve():
    gateway = ipaddress.IPv4Address(os.environ['WORKSTATION_GATEWAY'])
    lan = ipaddress.IPv4Network(os.environ['WORKSTATION_LAN'], strict=False)
    if gateway not in lan:
        raise ValueError('The gateway must belong to the workstation LAN')
    # Replace chain rules atomically, retaining approved sets if only the
    # helper restarts in the same namespace. A fresh namespace starts empty.
    rules = f"""
add table inet workstation
add set inet workstation allow_tcp {{ type ipv4_addr . inet_service; }}
add set inet workstation allow_udp {{ type ipv4_addr . inet_service; }}
add chain inet workstation output {{ type filter hook output priority filter; policy drop; }}
add chain inet workstation input {{ type filter hook input priority filter; policy accept; }}
flush chain inet workstation output
flush chain inet workstation input
add rule inet workstation output oifname "lo" accept
add rule inet workstation output ct direction reply ct state {{ established, related }} accept
add rule inet workstation output ip daddr {gateway} udp dport 53 accept
add rule inet workstation output ip daddr {gateway} tcp dport {{ 53, 7890, 7891 }} accept
add rule inet workstation output ip daddr {gateway} drop
add rule inet workstation output fib daddr type {{ local, broadcast, multicast }} drop
add rule inet workstation output ip daddr {lan} ip daddr . tcp dport @allow_tcp accept
add rule inet workstation output ip daddr {lan} ip daddr . udp dport @allow_udp accept
add rule inet workstation output ip daddr {lan} drop
add rule inet workstation output ip daddr {{ 0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.168.0.0/16, 224.0.0.0/4, 240.0.0.0/4 }} drop
add rule inet workstation output rt ip nexthop {gateway} accept
add rule inet workstation input iifname != "lo" meta pkttype {{ multicast, broadcast }} drop
"""
    subprocess.run(['nft', '-f', '-'], input=rules, text=True, check=True)
    # An abstract socket is scoped to this network namespace. A marker file
    # would survive the firewall after a namespace replacement.
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(SOCKET)
        server.listen()
        while True:
            connection, _ = server.accept()
            with connection:
                try:
                    handle_request(connection, lan, gateway)
                except OSError:
                    # A caller may disconnect while a rule transaction is completing.
                    continue


if __name__ == '__main__':
    if sys.argv[1:] == ['--ready']:
        ready()
    else:
        serve()
