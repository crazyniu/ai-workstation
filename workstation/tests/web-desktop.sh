#!/usr/bin/env bash
# Password-free private desktop; no VNC password or business mount is supplied.
set -euo pipefail
image=${1:?Usage: tests/web-desktop.sh IMAGE}
repo=$(cd "$(dirname "$0")/.." && pwd)
name="workstation-web-$(python3 -c 'import secrets; print(secrets.token_hex(5))')"
cleanup() {
    local result=$?
    if (( result != 0 )); then docker logs --tail 60 "$name" >&2 2>/dev/null || true; fi
    docker rm -f "$name" >/dev/null 2>&1 || true
}
trap cleanup EXIT
# Random test-only SSH credential; the web/VNC connection has no credential.
DEV_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_hex(16))') \
    docker run -d --name "$name" --network none --shm-size 512m \
    --cap-drop NET_ADMIN --cap-drop NET_RAW --security-opt no-new-privileges:true \
    --security-opt "seccomp=$repo/security/seccomp-chrome.json" \
    -e DEV_PASSWORD -e VNC_AUTH=none -e NOVNC_TLS=0 "$image" >/dev/null
wait_ready() {
    local i
    for ((i=0;i<90;i++)); do
        if docker exec "$name" python3 /etc/workstation/healthcheck.py >/dev/null 2>&1; then return; fi
        sleep 1
    done
    return 1
}
wait_ready
docker exec "$name" test ! -e /home/dev/.config/novnc/tls/server.key
docker exec -i "$name" python3 - --auth none --scheme http < "$repo/tests/web-desktop.py"
docker restart "$name" >/dev/null
wait_ready
docker exec "$name" test ! -e /home/dev/.config/novnc/tls/server.key
docker exec -i "$name" python3 - --auth none --scheme http < "$repo/tests/web-desktop.py"
printf 'PASS: private HTTP desktop survives restart without a password or TLS certificate.\n'
