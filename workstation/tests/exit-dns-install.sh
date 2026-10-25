#!/usr/bin/env bash
# Exercise the real opt-in installer in a private, disposable container.
set -euo pipefail
image=${1:?Usage: exit-dns-install.sh IMAGE}
repo=$(cd "$(dirname "$0")/.." && pwd)
name="workstation-dns-$(python3 -c 'import secrets; print(secrets.token_hex(5))')"
folder=$(mktemp -d)
cleanup() {
    local result=$?
    if (( result != 0 )); then docker logs --tail 40 "$name" >&2 2>/dev/null || true; fi
    docker rm -f "$name" >/dev/null 2>&1 || true
    docker network rm "$name" >/dev/null 2>&1 || true
    rm -rf "$folder"
}
trap cleanup EXIT
python3 - "$repo" "$folder" <<'PY'
import configparser, importlib.util, sys, urllib.request
from pathlib import Path
repo, folder = map(Path, sys.argv[1:])
spec=importlib.util.spec_from_file_location('exit_dns',repo/'scripts/configure-exit-dns.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
with urllib.request.urlopen(module.URL,timeout=120) as response:
    archive=response.read(64*1024*1024+1)
module.verified_artifacts(archive)
(folder/'release.tar.gz').write_bytes(archive)
config=configparser.RawConfigParser();config.read(repo/'runtime/supervisord.conf')
for section in list(config):
    if section.startswith('program:'):config.remove_section(section)
config['program:sentinel']={'command':'/usr/bin/sleep infinity','autostart':'true'}
with (folder/'supervisord.conf').open('w') as stream:config.write(stream)
PY
docker network create --internal "$name" >/dev/null
docker create --name "$name" --network "$name" \
    --cap-drop NET_ADMIN --cap-drop NET_RAW --security-opt no-new-privileges:true \
    -e HTTP_PROXY=http://127.0.0.1:9 -e HTTPS_PROXY=http://127.0.0.1:9 -e NO_PROXY= \
    --entrypoint /usr/bin/supervisord "$image" -n -c /etc/supervisor/supervisord.conf >/dev/null
docker cp "$folder/supervisord.conf" "$name:/etc/supervisor/supervisord.conf"
docker cp "$folder/release.tar.gz" "$name:/tmp/release.tar.gz"
docker start "$name" >/dev/null
for attempt in $(seq 1 40); do
    if docker exec "$name" supervisorctl -c /etc/supervisor/supervisord.conf pid sentinel >/dev/null 2>&1; then break; fi
    sleep 0.25
done
source_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$name")
gateway_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.Gateway}}{{end}}' "$name")
sentinel=$(docker exec "$name" supervisorctl -c /etc/supervisor/supervisord.conf pid sentinel)
docker exec -i "$name" python3 - "$source_ip" "$gateway_ip" <<'PY'
import importlib.util,shutil,sys
from pathlib import Path
# Only substitute the transport with a preverified local copy. Integrity checks,
# generated credentials, service startup and all filesystem changes remain real.
shutil.copyfile('/usr/local/bin/configure-workstation-exit-dns','/tmp/configure-exit-dns.py')
spec=importlib.util.spec_from_file_location('exit_dns','/tmp/configure-exit-dns.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.URL=Path('/tmp/release.tar.gz').as_uri()
module.install(sys.argv[1],sys.argv[2],5354)
try:module.install(sys.argv[1],sys.argv[2],5354)
except ValueError as error:assert 'Existing resolver' in str(error)
else:raise AssertionError('Reinstallation must not overwrite existing state')
PY
[[ $(docker exec "$name" supervisorctl -c /etc/supervisor/supervisord.conf pid sentinel) == "$sentinel" ]]
docker exec -i "$name" python3 - <<'PY'
from pathlib import Path
import json,socket,struct,subprocess,urllib.error,urllib.request
pid=subprocess.check_output(['supervisorctl','-c','/etc/supervisor/supervisord.conf','pid','workstation-exit-dns'],text=True).strip()
uid=next(x for x in Path('/proc/'+pid+'/status').read_text().splitlines() if x.startswith('Uid:'))
assert uid.split()[1:] == ['65534']*4
environment=dict(x.split(b'=',1) for x in Path('/proc/'+pid+'/environ').read_bytes().split(b'\0') if b'=' in x)
for key in [b'HTTP_PROXY',b'HTTPS_PROXY',b'ALL_PROXY',b'http_proxy',b'https_proxy',b'all_proxy']:
    assert not environment.get(key)
assert Path('/var/lib/workstation-exit-dns/AdGuardHome.yaml').stat().st_mode & 0o777 == 0o600
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:opener.open('http://127.0.0.1:3001/control/status',timeout=5)
except urllib.error.HTTPError as error:assert error.code==401
else:raise AssertionError('Management API must require authentication')
# This network is internal: both encrypted public upstreams are unreachable.
# A fresh query must fail rather than selecting another DNS path.
query=struct.pack('!HHHHHH',1234,0x100,1,0,0,0)+b'\x07example\x03com\0'+struct.pack('!HH',1,1)
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as stream:
    stream.settimeout(20);stream.sendto(query,('127.0.0.1',5354));reply,_=stream.recvfrom(16384)
header=struct.unpack('!HHHHHH',reply[:12]);assert header[0]==1234 and header[1]&15==2
print('PASS: isolated resolver runs unprivileged, requires API auth, and fails closed.')
PY
docker restart "$name" >/dev/null
for attempt in $(seq 1 60); do
    if docker exec "$name" supervisorctl -c /etc/supervisor/supervisord.conf status workstation-exit-dns 2>/dev/null | grep -q RUNNING; then break; fi
    sleep 0.25
done
docker exec "$name" supervisorctl -c /etc/supervisor/supervisord.conf status workstation-exit-dns | grep RUNNING
[[ $(docker inspect -f '{{json .Mounts}}' "$name") == '[]' ]]
printf 'PASS: optional DNS service persists and autostarts without data mounts.\n'
