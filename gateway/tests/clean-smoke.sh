#!/bin/bash
set -Eeuo pipefail
image=${1:?Usage: clean-smoke.sh IMAGE}
name=gateway-smoke-$(python3 -c 'import secrets; print(secrets.token_hex(5))')
cleanup(){ docker rm -f "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT
wait_ready(){
  for attempt in $(seq 1 45); do
    # The health check covers the services; Nginx must also be serving, or its error is in the log below.
    if docker exec "$name" python3 /opt/gateway/app/healthcheck.py >/dev/null 2>&1 \
      && docker exec "$name" python3 -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1/healthz", timeout=5)' >/dev/null 2>&1; then return; fi
    if [ "$attempt" = 45 ]; then docker logs --tail 50 "$name"; return 1; fi
    sleep 1
  done
}
docker run -d --name "$name" -e GATEWAY_MODE=false -e GATEWAY_ADMIN_PASSWORD=root "$image" >/dev/null
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
call('/api/auth/login',{'password':'root'})
assert not call('/api/cards')['cards']
c=yaml.safe_load((root/'mihomo/config.yaml').read_text())
assert not c.get('proxies') and not c.get('proxy-providers')
tailscale=call('/api/tailscale')
assert tailscale['state']=='NeedsLogin' and not tailscale['ips']
assert not call('/api/settings')['subscription']['url']
appearance={'fit':'cover','image':'','wallpaper':'coast','theme':'dark'}
assert call('/api/appearance',appearance)==appearance
call('/api/cards',{'name':'Local NAS','url':'http://192.0.2.15:8080','icon':'server'})
call('/api/password',{'current_password':'root','password':'test'})
assert call('/api/auth')['authenticated']
assert len(call('/api/cards')['cards'])==1
assert (root/'adguard/work/data/filters/1.txt').stat().st_size>1000000
with socket.create_connection(('127.0.0.1',22),timeout=5) as connection:assert connection.recv(100).startswith(b'SSH-2.0-')
import os,subprocess,tempfile
with tempfile.TemporaryDirectory() as folder:
    askpass=pathlib.Path(folder)/'askpass'
    askpass.write_text('#!/bin/sh\nprintf \"root\\n\"\n');askpass.chmod(0o700)
    result=subprocess.run(['ssh','-T','-o','PreferredAuthentications=password','-o','PubkeyAuthentication=no','-o','StrictHostKeyChecking=no','-o','UserKnownHostsFile=/dev/null','-o','ConnectTimeout=5','root@127.0.0.1','id -un'],env=dict(os.environ,DISPLAY=':0',SSH_ASKPASS_REQUIRE='force',SSH_ASKPASS=str(askpass)),stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=15,start_new_session=True,check=True)
    assert result.stdout.strip()=='root'
print('PASS fresh login, access control, empty private state, appearance, cards, password and SSH authentication')
PY
docker exec -i "$name" python3 - <<'PY'
import base64,json,os,socket,time,urllib.request,urllib.error,http.cookiejar
jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
def get(path):
    try:
        with client.open('http://127.0.0.1'+path,timeout=10) as response:return response.status,response.read()
    except urllib.error.HTTPError as error:return error.code,b''
def terminal(origin,command=None):
    # Open ttyd's WebSocket through Nginx, as the desktop window does, and run one command.
    cookie='; '.join(c.name+'='+c.value for c in jar)
    sock=socket.create_connection(('127.0.0.1',80),timeout=30)
    sock.sendall(('GET /terminal/ws HTTP/1.1\r\nHost: 127.0.0.1\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                  'Sec-WebSocket-Key: '+base64.b64encode(os.urandom(16)).decode()+'\r\nSec-WebSocket-Version: 13\r\n'
                  'Sec-WebSocket-Protocol: tty\r\nOrigin: '+origin+'\r\nCookie: '+cookie+'\r\n\r\n').encode())
    data=b''
    while b'\r\n\r\n' not in data:
        chunk=sock.recv(4096)
        if not chunk:break
        data+=chunk
    code=int(data.split(b' ')[1]);data=data.partition(b'\r\n\r\n')[2]
    if code!=101 or command is None:sock.close();return code,''
    def send(payload,opcode):
        mask=os.urandom(4);n=len(payload)
        sock.sendall(bytes([0x80|opcode])+(bytes([0x80|n]) if n<126 else bytes([0xfe])+n.to_bytes(2,'big'))+mask+bytes(b^mask[i%4] for i,b in enumerate(payload)))
    def need(size):
        nonlocal data
        while len(data)<size:
            chunk=sock.recv(65536)
            if not chunk:raise AssertionError('terminal closed early')
            data+=chunk
    send(json.dumps({'AuthToken':'','columns':120,'rows':30}).encode(),1)
    send(b'0'+command.encode()+b'\r',2)
    output=b'';deadline=time.time()+60
    while time.time()<deadline and b'TERMINAL-USER=root' not in output:
        need(2);size=data[1]&127;offset=2
        if size==126:need(4);size=int.from_bytes(data[2:4],'big');offset=4
        elif size==127:need(10);size=int.from_bytes(data[2:10],'big');offset=10
        need(offset+size);frame=data[offset:offset+size];data=data[offset+size:]
        if frame[:1]==b'0':output+=frame[1:]
    sock.close();return code,output.decode(errors='replace')
assert get('/terminal/')[0]==401,'anonymous terminal page'
assert terminal('http://127.0.0.1')[0]==401,'anonymous terminal socket'
request=urllib.request.Request('http://127.0.0.1/api/auth/login',data=json.dumps({'password':'test'}).encode(),headers={'Content-Type':'application/json'})
client.open(request,timeout=10).close()
with client.open('http://127.0.0.1/api/terminal',timeout=10) as response:assert json.load(response)=={'available':True,'reason':''}
code,page=get('/terminal/');assert code==200 and b'ttyd' in page.lower(),('terminal page',code)
assert terminal('http://elsewhere.invalid')[0]==403,'cross-origin terminal socket'
code,output=terminal('http://127.0.0.1','echo TERMINAL-USER=$(id -un)')
assert code==101 and 'TERMINAL-USER=root' in output,(code,output[-500:])
print('PASS terminal: login required, same-origin WebSocket only, root shell through Nginx and the private socket')
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
