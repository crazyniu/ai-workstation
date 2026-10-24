#!/usr/bin/env bash
# Deployment-contract acceptance: all workstation state stays in the container.
# No business container, host HOME, named volume, or bind mount is used.
set -euo pipefail
image=${1:?Usage: tests/internal-storage.sh IMAGE}
repo=$(cd "$(dirname "$0")/.." && pwd)
profile=${SECCOMP_PROFILE:-$repo/security/seccomp-chrome.json}
[[ -f $profile ]] || { printf 'Missing browser seccomp profile: %s\n' "$profile" >&2; exit 1; }
name="workstation-internal-$(python3 -c 'import secrets; print(secrets.token_hex(5))')"
fixture_dir=$(mktemp -d)
cleanup() {
    local result=$?
    if (( result != 0 )); then
        docker logs --tail 60 "$name" >&2 2>/dev/null || true
    fi
    docker rm -f "$name" >/dev/null 2>&1 || true
    rm -rf "$fixture_dir"
}
trap cleanup EXIT

# An image VOLUME would silently create an anonymous mount, even without -v.
docker image inspect "$image" | python3 -c '
import json,sys
image=json.load(sys.stdin)[0]
assert not image["Config"].get("Volumes"), "Image Config.Volumes must be empty"
print("PASS: image Config.Volumes is empty.")
'
python3 - "$fixture_dir/runtime.env" <<'PY'
from pathlib import Path
import secrets,sys
path=Path(sys.argv[1])
path.write_text('DEV_PASSWORD='+secrets.token_hex(16)+'\nVNC_PASSWORD='+secrets.token_hex(4)+'\n')
path.chmod(0o600)
PY
# --env-file loads runtime ENV into the test container; it creates no mount.
docker run -d --name "$name" --hostname workstation-internal-smoke --network none --shm-size 512m \
    --security-opt no-new-privileges:true --security-opt "seccomp=$profile" \
    --env-file "$fixture_dir/runtime.env" -e HTTPS_PROXY=http://127.0.0.1:9 "$image" >/dev/null

assert_no_mounts() {
    docker inspect "$name" | python3 -c '
import json,sys
container=json.load(sys.stdin)[0]
assert container["Mounts"] == [], "Runtime Mounts must be empty"
values=dict(item.split("=",1) for item in container["Config"]["Env"])
assert values.get("DEV_PASSWORD") and values.get("VNC_PASSWORD"), "Runtime ENV passwords are required"
assert not values.get("DEV_PASSWORD_FILE") and not values.get("VNC_PASSWORD_FILE"), "This fixture must test ENV credentials"
'
}
wait_desktop() {
    local attempt
    for ((attempt=1; attempt<=90; attempt++)); do
        if docker exec "$name" python3 /etc/workstation/healthcheck.py >/dev/null 2>&1; then
            return
        fi
        [[ $(docker inspect -f '{{.State.Running}}' "$name") == true ]] || break
        sleep 1
    done
    printf 'Internal-storage desktop did not become ready.\n' >&2
    return 1
}
dev_exec() {
    docker exec --user 1100:1100 -e HOME=/home/dev -e DISPLAY=:1 "$name" "$@"
}
assert_no_mounts
wait_desktop
assert_region() {
    docker exec -i --user 1100:1100 "$name" python3 - "$1" "$2" "$3" <<'PYREGION'
import os,pathlib,subprocess,sys
locale,language,timezone=sys.argv[1:]
pid=subprocess.check_output(['pgrep','-u','1100','-x','xfce4-session'],text=True).splitlines()[0]
session=dict(entry.split(b'=',1) for entry in pathlib.Path('/proc/'+pid+'/environ').read_bytes().split(b'\0') if b'=' in entry)
for key,value in {'LANG':locale,'LC_ALL':locale,'LANGUAGE':language,'TZ':timezone}.items():
    assert session.get(key.encode())==value.encode(),key
assert pathlib.Path('/etc/timezone').read_text().strip()==timezone
assert pathlib.Path('/etc/localtime').resolve()==pathlib.Path('/usr/share/zoneinfo/'+timezone).resolve()
print('PASS: XFCE and system region:',locale,language,timezone)
PYREGION
    docker exec "$name" runuser -l dev -c 'test "$LANG" = "$1" && test "$LANGUAGE" = "$2" && test "$TZ" = "$3"' sh "$1" "$2" "$3"
}
assert_region en_US.UTF-8 en_US:en America/Los_Angeles
docker exec -i --user 1100:1100 "$name" python3 - <<'PYPROXY'
import pathlib,subprocess
pid=subprocess.check_output(['pgrep','-u','1100','-x','xfce4-session'],text=True).splitlines()[0]
assert b'HTTPS_PROXY=http://127.0.0.1:9' in pathlib.Path('/proc/'+pid+'/environ').read_bytes().split(b'\0')
print('PASS: runtime proxy reaches the ordinary-user XFCE session.')
PYPROXY
docker exec -i "$name" python3 - < "$repo/tests/auth-smoke.py"

docker exec -i --user 1100:1100 -e HOME=/home/dev "$name" python3 - <<'PY'
import os
from pathlib import Path
assert os.getuid()==1100 and os.getgid()==1100
home=Path('/home/dev')
(home/'Projects/internal-storage-smoke.txt').write_text('container-owned-persistence\n')
config=home/'.codex/config.toml'
config.write_text(config.read_text()+'\n# internal-storage-preserve-settings\n')
PY
dev_exec gh config set git_protocol ssh
first_keys=$(docker exec "$name" sh -c 'for key in /etc/ssh/keys/ssh_host_*_key.pub; do ssh-keygen -lf "$key"; done')
[[ -n $first_keys ]]
# Existing containers change region through their internal file, without
# recreating the container or moving its HOME, MCP settings or SSH identity.
docker exec -i "$name" python3 - <<'PYREGION'
import json,pathlib
path=pathlib.Path('/etc/workstation/region.json')
path.write_text(json.dumps({'country':'TW','language':'zh','timezone':'Asia/Taipei'})+'\n')
path.chmod(0o600)
PYREGION
docker restart "$name" >/dev/null
assert_no_mounts
wait_desktop
assert_region zh_TW.UTF-8 zh_TW:zh Asia/Taipei
docker exec -i --user 1100:1100 "$name" python3 - < "$repo/tests/desktop-recovery.py"
docker exec -i "$name" python3 - < "$repo/tests/auth-smoke.py"
dev_exec sh -c 'test "$(cat /home/dev/Projects/internal-storage-smoke.txt)" = container-owned-persistence && grep -q internal-storage-preserve-settings /home/dev/.codex/config.toml'
[[ $(dev_exec gh config get git_protocol) == ssh ]]
second_keys=$(docker exec "$name" sh -c 'for key in /etc/ssh/keys/ssh_host_*_key.pub; do ssh-keygen -lf "$key"; done')
[[ $first_keys == "$second_keys" ]]
printf 'PASS: runtime Mounts=[]; ENV SSH/VNC authentication, HOME data, user settings, gh configuration, and SSH host keys survive container restart.\n'
printf 'PASS: internal container storage acceptance completed; the disposable container will be removed.\n'
