#!/bin/bash
set -euo pipefail
image=${1:?native test image required}
name=ai-native-smoke-$RANDOM
cleanup() { docker logs --tail 30 "$name" >&2 || true; docker rm -f "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker run -d --name "$name" --shm-size 512m --security-opt no-new-privileges:true \
    --security-opt "seccomp=$(pwd)/workstation/security/seccomp-chrome.json" "$image" >/dev/null
for i in $(seq 1 120); do
    if docker exec -e WORKSTATION_SSH_PORT=2222 "$name" python3 /etc/workstation/healthcheck.py >/dev/null 2>&1 && \
       docker exec "$name" curl --noproxy '*' -fsS http://127.0.0.1:8080/healthz >/dev/null; then break; fi
    sleep 1
done
docker exec -e WORKSTATION_SSH_PORT=2222 "$name" python3 /etc/workstation/healthcheck.py
docker exec -e DATA_DIR=/var/lib/ai-gateway "$name" python3 /opt/gateway/app/healthcheck.py
docker exec --user 1100:1100 -e HOME=/home/dev -e DISPLAY=:1 "$name" bash /opt/workstation/scripts/verify-tools.sh
docker exec -i "$name" python3 - <<'PY'
import json, pathlib, socket, urllib.request
for port in [2222,2223]:
    with socket.create_connection(('127.0.0.1',port),timeout=3) as connection:
        assert connection.recv(64).startswith(b'SSH-')
request=urllib.request.Request('http://127.0.0.1:8080/api/auth/login',data=b'{"password":"root"}',headers={'Content-Type':'application/json'})
with urllib.request.urlopen(request,timeout=5) as response: assert response.status==200
assert pathlib.Path('/etc/nginx/nginx.conf').read_text()!=pathlib.Path('/run/gateway/nginx.conf').read_text()
assert 'Port 2222' in pathlib.Path('/etc/workstation/sshd_config').read_text()
assert 'native' in pathlib.Path('/etc/systemd/system/ai-workstation.service').read_text()
print('PASS: native provisioning, host root preservation, private service configs, web login and both SSH greetings.')
PY
