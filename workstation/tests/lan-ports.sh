#!/usr/bin/env bash
# Exercise the numbered management menu in the same split network namespace as LAN deployments.
set -euo pipefail
image=${1:?Usage: lan-ports.sh IMAGE}
guard=$(docker run -d --read-only --network none --cap-drop ALL --cap-add NET_ADMIN \
    --security-opt no-new-privileges:true -e WORKSTATION_GATEWAY=192.0.2.1 -e WORKSTATION_LAN=192.0.2.0/24 \
    --entrypoint python3 "$image" /etc/workstation/network-guard.py)
client=
cleanup() {
    if [[ -n $client ]]; then docker rm -f "$client" >/dev/null; fi
    docker rm -f "$guard" >/dev/null
}
trap cleanup EXIT
client=$(docker run -d --network "container:$guard" --cap-drop NET_ADMIN --cap-drop NET_RAW \
    -e WORKSTATION_LAN_GUARD=required -e WORKSTATION_INITIAL_ORCA_ENDPOINT=192.0.2.2:6768 \
    --entrypoint sleep "$image" infinity)
for attempt in {1..30}; do
    if docker exec "$client" python3 /etc/workstation/network-guard.py --ready 2>/dev/null; then break; fi
    sleep 0.2
done
init() { docker exec "$client" python3 -I /etc/workstation/lan_ports.py init; }
menu() { printf '%s\n' 7 "$@" 0 0 | docker exec -i "$client" /usr/local/bin/niu.sh; }
allowed() { docker exec "$guard" nft get element inet workstation "allow_$1" "{ $2 . $3 }" >/dev/null 2>&1; }

init
allowed tcp 192.0.2.2 6768
menu 3 1 0
allowed tcp 192.0.2.2 6768
menu 3 1 1
if allowed tcp 192.0.2.2 6768; then echo 'Revoked rule still active' >&2; exit 1; fi

menu 2 192.0.2.3 5353 udp 0
if allowed udp 192.0.2.3 5353; then echo 'Cancelled rule was applied' >&2; exit 1; fi
menu 2 192.0.2.3 5353 udp 1
allowed udp 192.0.2.3 5353
if allowed tcp 192.0.2.3 5353; then echo 'Wrong protocol was opened' >&2; exit 1; fi
if allowed udp 192.0.2.4 5353; then echo 'Wrong destination was opened' >&2; exit 1; fi

docker exec "$guard" nft flush set inet workstation allow_udp
docker restart "$client" >/dev/null
init
allowed udp 192.0.2.3 5353
if allowed tcp 192.0.2.2 6768; then echo 'Removed first-boot exception was reintroduced' >&2; exit 1; fi
echo 'PASS LAN port approvals, cancellation, revocation, protocol scope and restart persistence.'
