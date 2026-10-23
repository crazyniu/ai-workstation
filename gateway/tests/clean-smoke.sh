#!/bin/bash
set -Eeuo pipefail
image=${1:?Usage: clean-smoke.sh IMAGE}
name=gateway-smoke-$(python3 -c 'import secrets; print(secrets.token_hex(5))')
cleanup(){ docker rm -f "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT
wait_ready(){
  for attempt in $(seq 1 45); do
    if docker exec "$name" python3 /opt/gateway/app/healthcheck.py >/dev/null 2>&1; then return; fi
    if [ "$attempt" = 45 ]; then docker logs --tail 50 "$name"; return 1; fi
    sleep 1
  done
}
docker run -d --name "$name" --cap-add NET_ADMIN --device /dev/net/tun -e GATEWAY_MODE=false -e GATEWAY_ADMIN_PASSWORD=admin "$image" >/dev/null
docker inspect "$name" --format '{{json .Mounts}}' | python3 -c 'import json,sys; assert not json.load(sys.stdin), "Business data must stay inside the container; unexpected mounts"'
wait_ready
docker exec -i "$name" python3 - <<'PY'
import json,urllib.request,urllib.error,http.cookiejar,pathlib,socket,yaml
root=pathlib.Path('/data')
jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
def call(path,data=None):
    request=urllib.request.Request('http://127.0.0.1'+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
    with client.open(request,timeout=10) as response:return json.load(response)
assert call('/api/auth')['initialized']
try:call('/api/cards');raise AssertionError('anonymous cards accepted')
except urllib.error.HTTPError as error:assert error.code==401
call('/api/auth/login',{'password':'admin'})
assert not call('/api/cards')['cards']
c=yaml.safe_load((root/'mihomo/config.yaml').read_text())
assert not c.get('proxies') and not c.get('proxy-providers')
tailscale=call('/api/tailscale')
assert tailscale['state']=='NeedsLogin' and not tailscale['ips']
assert not call('/api/settings')['subscription']['url']
appearance={'fit':'cover','image':'','wallpaper':'coast','theme':'dark'}
assert call('/api/appearance',appearance)==appearance
call('/api/cards',{'name':'Local NAS','url':'http://192.0.2.15:8080','icon':'server'})
call('/api/password',{'current_password':'admin','password':'test'})
assert call('/api/auth')['authenticated']
assert len(call('/api/cards')['cards'])==1
assert (root/'adguard/work/data/filters/1.txt').stat().st_size>1000000
with socket.create_connection(('127.0.0.1',22),timeout=5) as connection:assert connection.recv(100).startswith(b'SSH-2.0-')
import os,subprocess,tempfile
with tempfile.TemporaryDirectory() as folder:
    askpass=pathlib.Path(folder)/'askpass'
    askpass.write_text('#!/bin/sh\nprintf \"admin\\n\"\n');askpass.chmod(0o700)
    result=subprocess.run(['ssh','-T','-o','PreferredAuthentications=password','-o','PubkeyAuthentication=no','-o','StrictHostKeyChecking=no','-o','UserKnownHostsFile=/dev/null','-o','ConnectTimeout=5','admin@127.0.0.1','id -un'],env=dict(os.environ,DISPLAY=':0',SSH_ASKPASS_REQUIRE='force',SSH_ASKPASS=str(askpass)),stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=15,start_new_session=True,check=True)
    assert result.stdout.strip()=='admin'
print('PASS fresh login, access control, empty private state, appearance, cards, password and SSH authentication')
PY
docker restart "$name" >/dev/null
wait_ready
docker exec -i "$name" python3 - <<'PY'
import json,urllib.request,http.cookiejar
jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
def call(path,data=None):
    with client.open(urllib.request.Request('http://127.0.0.1'+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'}),timeout=10) as response:return json.load(response)
call('/api/auth/login',{'password':'test'})
assert call('/api/appearance')['theme']=='dark'
assert call('/api/cards')['cards'][0]['name']=='Local NAS'
print('PASS password, appearance and cards preserved after container restart (no business mounts)')
PY
