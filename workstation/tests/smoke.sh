#!/usr/bin/env bash
# Isolated, disposable image acceptance; never targets an existing workstation.
# Named volumes and the secret bind below are explicit compatibility/security
# fixtures, including the independent HOME symlink attack check. They do not
# describe the mount-free deployment contract; internal-storage.sh tests that.
set -euo pipefail
image=${1:?Usage: tests/smoke.sh IMAGE}
repo=$(cd "$(dirname "$0")/.." && pwd)
profile=${SECCOMP_PROFILE:-$repo/security/seccomp-chrome.json}
[[ -f $profile ]] || { printf 'Missing browser seccomp profile: %s\n' "$profile" >&2; exit 1; }
name="workstation-smoke-$(python3 -c 'import secrets; print(secrets.token_hex(5))')"
home_volume="$name-home"
keys_volume="$name-keys"
secret_dir=$(mktemp -d)
cleanup() {
    local result=$?
    if (( result != 0 )); then
        docker logs --tail 60 "$name" >&2 2>/dev/null || true
        if [[ -f $secret_dir/chrome-stderr.log ]]; then
            tail -n 30 "$secret_dir/chrome-stderr.log" >&2
        fi
    fi
    docker rm -f "$name" >/dev/null 2>&1 || true
    docker volume rm "$home_volume" "$keys_volume" >/dev/null 2>&1 || true
    rm -rf "$secret_dir"
}
trap cleanup EXIT
python3 - "$secret_dir" <<'PY'
import secrets, sys
from pathlib import Path
folder = Path(sys.argv[1])
for name, size in [('dev-password', 16), ('vnc-password', 4)]:
    target = folder/name
    target.write_text(secrets.token_hex(size)+'\n')
    target.chmod(0o600)
PY

docker volume create "$home_volume" >/dev/null
docker volume create "$keys_volume" >/dev/null
docker run -d --name "$name" --hostname workstation-smoke --network none --shm-size 512m \
    --security-opt no-new-privileges:true --security-opt "seccomp=$profile" \
    --mount "type=volume,src=$home_volume,dst=/home/dev" \
    --mount "type=volume,src=$keys_volume,dst=/etc/ssh/keys" \
    --mount "type=bind,src=$secret_dir,dst=/run/secrets,readonly" \
    -e DEV_PASSWORD_FILE=/run/secrets/dev-password \
    -e VNC_PASSWORD_FILE=/run/secrets/vnc-password "$image" >/dev/null

wait_desktop() {
    local attempt
    for ((attempt=1; attempt<=60; attempt++)); do
        if docker exec "$name" python3 /etc/workstation/healthcheck.py >/dev/null 2>&1; then
            return
        fi
        [[ $(docker inspect -f '{{.State.Running}}' "$name") == true ]] || break
        sleep 1
    done
    docker logs --tail 40 "$name" >&2
    printf 'Desktop did not become ready.\n' >&2
    return 1
}
wait_desktop
docker exec -i --user 1100:1100 "$name" python3 - < "$repo/tests/desktop-recovery.py"
docker exec "$name" test -x /usr/local/bin/reset-claude-user
# Exercise the installed command against a dedicated temporary HOME only.
# No real account state is removed by startup or acceptance.
docker exec -i --user 1100:1100 "$name" python3 - <<'PYRESET'
import json,os,pathlib,subprocess,tempfile
with tempfile.TemporaryDirectory(prefix='claude-reset-smoke-') as folder:
    home=pathlib.Path(folder)
    config=home/'.claude'
    config.mkdir()
    account=home/'.claude.json'
    account.write_text(json.dumps({'userID':'fixture-user','mcpServers':{'keep':{}}}))
    credentials=config/'.credentials.json'
    credentials.write_text(json.dumps({'claudeAiOauth':{'accessToken':'fixture-only'},'mcpOAuth':{'keep':{}}}))
    environment={k:v for k,v in os.environ.items() if not k.startswith('ANTHROPIC_') and not k.startswith('CLAUDE_CODE_OAUTH_') and k!='CLAUDE_CONFIG_DIR'}
    command=['reset-claude-user','--home',str(home)]
    subprocess.run(command,env=environment,check=True,stdout=subprocess.DEVNULL)
    assert 'userID' in json.loads(account.read_text()),'Preview changed account'
    subprocess.run(command+['--apply'],env=environment,check=True,stdout=subprocess.DEVNULL)
    assert json.loads(account.read_text())=={'mcpServers':{'keep':{}}}
    assert json.loads(credentials.read_text())=={'mcpOAuth':{'keep':{}}}
print('PASS: installed Claude reset command previews safely and preserves MCP configuration/credentials.')
PYRESET
docker exec -i "$name" python3 - < "$repo/tests/auth-smoke.py"

dev_exec() {
    docker exec --user 1100:1100 -e HOME=/home/dev -e DISPLAY=:1 "$name" "$@"
}
# Root is locked without an optional runtime root-password secret. Host keys are generated now.
docker exec "$name" python3 -c '
from pathlib import Path
shadow=dict(line.split(":",2)[:2] for line in Path("/etc/shadow").read_text().splitlines())
assert shadow["root"].startswith(("!","*"))
assert list(Path("/etc/ssh/keys").glob("ssh_host_*_key"))
'
# docker exec needs -i for stdin scripts; keep all assertions in one bounded check.
docker exec -i --user 1100:1100 -e HOME=/home/dev -e DISPLAY=:1 "$name" python3 - <<'PY'
import json, os, pathlib, shutil, socket, stat, tomllib
assert os.getuid()==1100 and os.getgid()==1100 and set(os.getgroups())<={1100}
status=dict(line.split(':',1) for line in pathlib.Path('/proc/self/status').read_text().splitlines() if ':' in line)
assert int(status['CapEff'].strip(),16)==0
assert status['NoNewPrivs'].strip()=='1'
assert not os.access('/root',os.R_OK)
assert not os.access('/var/run/docker.sock',os.R_OK|os.W_OK)
assert not shutil.which('sudo')
for file in ['/usr/local/bin/codex','/usr/local/bin/claude','/usr/local/bin/workstation-mcp']:
    assert pathlib.Path(file).stat().st_uid==0 and not os.access(file,os.W_OK),file
home=pathlib.Path('/home/dev')
for filename in ['.codex/config.toml','.claude.json']:
    path=home/filename
    assert path.stat().st_uid==1100 and stat.S_IMODE(path.stat().st_mode)==0o600
servers=tomllib.loads((home/'.codex/config.toml').read_text())['mcp_servers']
assert set(['context7','playwright','chrome-devtools','godot','unity','github'])<=set(servers)
claude=json.loads((home/'.claude.json').read_text())['mcpServers']
assert set(servers)<=set(claude)
assert '--sandbox' in servers['playwright']['args']
for server in servers.values():
    assert '--no-sandbox' not in server.get('args',[])
for port in [22,5901]:
    with socket.create_connection(('127.0.0.1',port),timeout=5) as conn:
        greeting=conn.recv(256)
        assert greeting.startswith(b'SSH-' if port==22 else b'RFB '),(port,greeting)
for filename in ['codex.desktop','claude.desktop','godot.desktop','google-chrome.desktop','code.desktop']:
    assert os.access(home/'Desktop'/filename,os.X_OK),filename
(home/'Projects/persistence-smoke.txt').write_text('persisted\n')
(home/'.codex/config.toml').write_text((home/'.codex/config.toml').read_text()+'\n# preserve-my-settings-smoke\n')
print('PASS: user permissions, MCP registration, service greetings, and desktop launchers.')
PY
[[ $(dev_exec xfconf-query -c xfce4-panel -p /panels/panel-1/size) == 42 ]]
[[ $(dev_exec xfconf-query -c xfce4-panel -p /plugins/plugin-31) == applicationsmenu ]]
printf 'PASS: the configured XFCE panel loaded without falling back to defaults.\n'
dev_exec timeout 240 bash /opt/workstation/scripts/verify-tools.sh
dev_exec gh config set git_protocol ssh
# No --no-sandbox or privileged capability workaround is used for this browser check.
dev_exec unshare -Ur true
dev_exec timeout 45 google-chrome-stable --headless --no-first-run --disable-gpu \
    --disable-background-networking --user-data-dir=/home/dev/.cache/chrome-smoke \
    --dump-dom 'data:text/html,<html><body><script>document.body.textContent="WORKSTATION_CHROME_PASS";</script></body></html>' \
    2>"$secret_dir/chrome-stderr.log" | grep -q '<body>WORKSTATION_CHROME_PASS</body>'
printf 'PASS: sandbox-enabled Chrome launched as dev and executed JavaScript.\n'
# Capture generated host-key fingerprints without copying private key material out.
first_keys=$(docker exec "$name" sh -c 'for key in /etc/ssh/keys/ssh_host_*_key.pub; do ssh-keygen -lf "$key"; done')
docker restart "$name" >/dev/null
wait_desktop
docker exec -i "$name" python3 - < "$repo/tests/auth-smoke.py"
# shellcheck disable=SC2016 # Expansion must happen inside the test container.
dev_exec sh -c 'test "$(cat /home/dev/Projects/persistence-smoke.txt)" = persisted && grep -q preserve-my-settings-smoke /home/dev/.codex/config.toml'
[[ $(dev_exec gh config get git_protocol) == ssh ]]
second_keys=$(docker exec "$name" sh -c 'for key in /etc/ssh/keys/ssh_host_*_key.pub; do ssh-keygen -lf "$key"; done')
[[ $first_keys == "$second_keys" ]]
printf 'PASS: HOME content, user configuration, and SSH host keys survive restart.\n'
# Confirm the session stays alive after browser work rather than only checking initial startup.
sleep 3
docker exec "$name" sh -c 'pgrep -u 1100 -x xfce4-session >/dev/null && pgrep -u 1100 -x xfdesktop >/dev/null'
# A dev-controlled HOME must never redirect root bootstrap writes/chown into host keys.
# The malicious restart may fail safely; the independent read-only helper checks the volume.
docker exec "$name" python3 -c 'from pathlib import Path; p=Path("/etc/ssh/keys/vnc-symlink-guard"); p.write_text("ROOT_OWNED_GUARD_UNCHANGED\n"); p.chmod(0o644)'
docker exec -i --user 1100:1100 -e HOME=/home/dev "$name" python3 - <<'PYTEST'
from pathlib import Path
home=Path('/home/dev')
(home/'Projects').rename(home/'Projects.before-symlink-check')
(home/'Projects').symlink_to('/etc/ssh/keys',target_is_directory=True)
password=home/'.config/tigervnc/passwd'
password.unlink()
password.symlink_to('/etc/ssh/keys/vnc-symlink-guard')
PYTEST
docker restart "$name" >/dev/null
sleep 2
docker run --rm --network none --security-opt no-new-privileges:true \
    --entrypoint python3 --mount "type=volume,src=$keys_volume,dst=/guard,readonly" "$image" -c '
from pathlib import Path
keys=Path("/guard")
assert keys.stat().st_uid==0, "HOME symlink changed SSH keys directory ownership"
guard=keys/"vnc-symlink-guard"
assert guard.stat().st_uid==0
assert guard.read_text()=="ROOT_OWNED_GUARD_UNCHANGED\n", "HOME symlink redirected a privileged password write"
'
printf 'PASS: dev HOME symlinks cannot redirect privileged bootstrap ownership or password writes.\n'
printf 'PASS: isolated image smoke completed; no live workstation was modified.\n'
