#!/usr/bin/env bash
# Online acceptance in a new disposable container; no existing deployment or login.
set -euo pipefail
image=${1:?Usage: updates.sh IMAGE}
repo=$(cd "$(dirname "$0")/.." && pwd)
name="workstation-updates-$(python3 -c 'import secrets; print(secrets.token_hex(5))')"
fixture=$(mktemp -d)
cleanup() {
    result=$?
    docker rm -f "$name" >/dev/null 2>&1 || true
    rm -rf "$fixture"
    exit "$result"
}
trap cleanup EXIT
python3 - "$fixture/env" <<'PY'
from pathlib import Path
import secrets,sys
password=secrets.token_hex(16)
path=Path(sys.argv[1]); path.write_text('DEV_PASSWORD='+password+'\nVNC_PASSWORD='+secrets.token_hex(4)+'\nWORKSTATION_UPDATE_TEST_PASSWORD='+password+'\n')
path.chmod(0o600)
PY
docker run -d --name "$name" --shm-size 512m --cap-drop NET_ADMIN --cap-drop NET_RAW \
    --security-opt no-new-privileges:false --security-opt "seccomp=$repo/security/seccomp-chrome.json" \
    --env-file "$fixture/env" "$image" >/dev/null
wait_ready() {
    for ((attempt=0;attempt<90;attempt++)); do
        if docker exec "$name" python3 /etc/workstation/healthcheck.py >/dev/null 2>&1; then return; fi
        sleep 1
    done
    echo 'Upgrade fixture failed its health check.' >&2
    # Name the failing check and show the desktop processes and recent service
    # output. The fixture's passwords are random and never printed.
    docker exec "$name" python3 /etc/workstation/healthcheck.py 2>&1 | tail -n 3 >&2 || true
    docker exec "$name" ps -u 1100 -o comm=,stat= >&2 || true
    docker logs --tail 40 "$name" >&2 || true
    return 1
}
wait_ready
# Resolve the image account with its supplementary groups, like a real desktop session.
# An explicit UID:GID omits the existing sudo group and invalidates this fixture.
docker exec --user dev "$name" sh -c "id -Gn | tr ' ' '\\n' | grep -qx sudo"
# The initial Orca is a stopped fixture, never an authenticated personal server.
# update_orca must replace it with the real verified official release.
docker exec -i "$name" bash -s <<'SETUP'
set -euo pipefail
mkdir -p /home/dev/.local/share/orca-server/releases/ci-before/bin
printf '#!/bin/sh\nexit 0\n' > /home/dev/.local/share/orca-server/releases/ci-before/bin/orca-ide
chmod 755 /home/dev/.local/share/orca-server/releases/ci-before/bin/orca-ide
ln -s releases/ci-before /home/dev/.local/share/orca-server/current
chown -R dev:dev /home/dev/.local/share/orca-server
cat > /etc/supervisor/conf.d/orca.conf <<'CONF'
[program:orca]
command=/home/dev/.local/share/orca-server/current/bin/orca-ide
user=dev
autostart=false
autorestart=false
stdout_logfile=/dev/null
stderr_logfile=/dev/null
CONF
supervisorctl reread
supervisorctl update
cat > /home/dev/.local/upgrade-askpass <<'ASKPASS'
#!/bin/sh
printf '%s\n' "$WORKSTATION_UPDATE_TEST_PASSWORD"
ASKPASS
chown dev:dev /home/dev/.local/upgrade-askpass
chmod 700 /home/dev/.local/upgrade-askpass
printf 'project-preserved\n' > /home/dev/Projects/upgrade-fixture.txt
chown dev:dev /home/dev/Projects/upgrade-fixture.txt
SETUP
# Capture only hashes, never credential contents, in CI output.
state() {
    docker exec "$name" python3 -c 'import hashlib;from pathlib import Path;shadow=[line.split(":")[0:2] for line in Path("/etc/shadow").read_text().splitlines() if line.split(":")[0] in ("dev","root")];print(hashlib.sha256(repr(shadow).encode()).hexdigest());paths=("/home/dev/.config/tigervnc/passwd","/home/dev/.codex/config.toml","/home/dev/.claude.json","/home/dev/Projects/upgrade-fixture.txt","/etc/ssh/keys/ssh_host_ed25519_key");print("\n".join(hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths))'
}
state > "$fixture/before"
targets=('All APT packages' 'Node.js and npm' 'uv and installed tools' 'Codex CLI' 'Claude Code' 'MCP servers' noVNC 'VS Code extensions' 'Orca Server')
for spec in 'Google Chrome:google-chrome-stable' 'Chromium:chromium' 'VS Code:code' 'Claude Desktop:claude-desktop' 'KasmVNC:kasmvncserver'; do
    if docker exec "$name" dpkg-query -W -f='${db:Status-Status}' "${spec#*:}" 2>/dev/null | grep -qx installed; then targets+=("${spec%%:*}"); fi
done
failed=()
for target in "${targets[@]}" all; do
    echo "REAL upgrade: $target"
    if docker exec --user dev -e HOME=/home/dev -e DISPLAY=:1 \
        -e SUDO_ASKPASS=/home/dev/.local/upgrade-askpass "$name" niu.sh --update "$target" --yes; then
        echo "PASS upgrade: $target"
    else
        echo "FAIL upgrade: $target" >&2
        failed+=("$target")
    fi
done
docker exec --user dev -e HOME=/home/dev "$name" sh -c 'codex --version && claude --version && node --version && uv --version'
docker exec --user dev -e HOME=/home/dev -e DISPLAY=:1 "$name" node /opt/workstation/scripts/mcp-smoke.mjs
docker exec "$name" test -x /home/dev/.local/share/orca-server/current/bin/orca-ide
docker exec "$name" sh -c 'test "$(readlink /home/dev/.local/share/orca-server/current)" != releases/ci-before'
state > "$fixture/after-upgrade"
cmp "$fixture/before" "$fixture/after-upgrade"
# Prove that a user-selected password survives restart, independently of initial ENV.
docker exec -i "$name" python3 - <<'PASSWORDS'
from pathlib import Path
import secrets,subprocess
subprocess.run(['chpasswd'], input=('dev:'+secrets.token_hex(16)+'\n').encode(),check=True)
encoded=subprocess.run(['tigervncpasswd','-f'],input=(secrets.token_hex(4)+'\n').encode(),stdout=subprocess.PIPE,check=True).stdout
Path('/home/dev/.config/tigervnc/passwd').write_bytes(encoded)
PASSWORDS
state > "$fixture/before-restart"
docker restart "$name" >/dev/null
wait_ready
state > "$fixture/after"
cmp "$fixture/before-restart" "$fixture/after"
if (( ${#failed[@]} )); then printf 'Upgrade failures: %s\n' "${failed[*]}" >&2; exit 1; fi
echo 'PASS: real single/batch upgrades and state preservation across restart.'
