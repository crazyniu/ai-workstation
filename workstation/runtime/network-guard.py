#!/usr/bin/python3
"""Own the workstation LAN namespace; desktop processes never receive NET_ADMIN."""
import ipaddress
import os
import socket
import subprocess
import sys

READY = b'\0ai-workstation-lan-firewall'


def ready():
    with socket.socket(socket.AF_UNIX) as client:
        client.connect(READY)


def serve():
    gateway = ipaddress.IPv4Address(os.environ['WORKSTATION_GATEWAY'])
    lan = ipaddress.IPv4Network(os.environ['WORKSTATION_LAN'], strict=False)
    if gateway not in lan:
        raise ValueError('The gateway must belong to the workstation LAN')
    # A single nft transaction also replaces an existing policy on restart.
    rules = f"""
add table inet workstation
delete table inet workstation
table inet workstation {{
  chain output {{
    type filter hook output priority filter; policy drop;
    oifname "lo" accept
    ct direction reply ct state {{ established, related }} accept
    ip daddr {gateway} udp dport 53 accept
    ip daddr {gateway} tcp dport {{ 53, 7890, 7891 }} accept
    ip daddr {lan} drop
    ip daddr {{ 0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.168.0.0/16, 224.0.0.0/4, 240.0.0.0/4 }} drop
    fib daddr type {{ local, broadcast, multicast }} drop
    rt ip nexthop {gateway} accept
  }}
  chain input {{
    type filter hook input priority filter; policy accept;
    iifname != "lo" meta pkttype {{ multicast, broadcast }} drop
  }}
}}
"""
    subprocess.run(['nft', '-f', '-'], input=rules, text=True, check=True)
    # An abstract socket is scoped to this network namespace. A marker file
    # would survive the firewall after a namespace replacement.
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(READY)
        server.listen()
        while True:
            connection, _ = server.accept()
            connection.close()


if __name__ == '__main__':
    if sys.argv[1:] == ['--ready']:
        ready()
    else:
        serve()
