#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C.UTF-8 LANGUAGE=en

base=/opt/workstation
cli_prefix="$HOME/.local/share/workstation-cli"
fetch=(curl --fail --location --silent --show-error --retry 3)
admin=(sudo -H --preserve-env=http_proxy,https_proxy,no_proxy,HTTP_PROXY,HTTPS_PROXY,NO_PROXY env LC_ALL=C.UTF-8 LANGUAGE=en)
apt=("${admin[@]}" DEBIAN_FRONTEND=noninteractive apt-get -o Dpkg::Options::=--force-confold)

# Replace files by rename so running binaries remain usable during the update.
sync_files=("${admin[@]}" rsync -a --checksum --chown=root:root --chmod=a+rX,go-w --delay-updates)

latest_tag() {
    "${fetch[@]}" "https://api.github.com/repos/$1/releases/latest" |
        python3 -c 'import json, sys; print(json.load(sys.stdin)["tag_name"])'
}

update_apt() {
    "${apt[@]}" -o APT::Update::Error-Mode=any update
    "${apt[@]}" --with-new-pkgs upgrade -y
}

update_node() {
    node_major=$(node -p 'process.versions.node.split(".")[0]')
    "${fetch[@]}" "https://nodejs.org/dist/latest-v$node_major.x/SHASUMS256.txt" -o node-checksums
    read -r digest archive < <(awk -v arch="$node_arch" '$2 ~ ("-linux-" arch "\\.tar\\.xz$") {print; exit}' node-checksums)
    release=${archive%-linux-*}
    version=${release#node-}
    if [[ $(node --version) != "$version" ]]; then
        "${fetch[@]}" "https://nodejs.org/dist/$version/$archive" -o "$archive"
        printf '%s  %s\n' "$digest" "$archive" | sha256sum --check --status
        tar -xJf "$archive"
        distribution=${archive%.tar.xz}
        for module in "$distribution"/lib/node_modules/*; do
            "${sync_files[@]}" --delete-delay "$module/" "/opt/node/lib/node_modules/${module##*/}/"
        done
        "${sync_files[@]}" --exclude='/lib/node_modules/' "$distribution/" /opt/node/
    fi
}

update_uv() {
    uv_tag=$(latest_tag astral-sh/uv)
    if [[ $(uv --version | cut -d' ' -f2) != "${uv_tag#v}" ]]; then
        archive="uv-$uv_arch-unknown-linux-gnu.tar.gz"
        url="https://github.com/astral-sh/uv/releases/download/$uv_tag/$archive"
        "${fetch[@]}" "$url" -o "$archive"
        "${fetch[@]}" "$url.sha256" -o uv-checksum
        sha256sum --check --status uv-checksum
        tar -xzf "$archive"
        "${sync_files[@]}" "${archive%.tar.gz}"/{uv,uvx} /usr/local/bin/
    fi
    uv tool upgrade --all
}

update_novnc() {
    novnc_tag=$(latest_tag novnc/noVNC)
    if [[ $(node -p "require('$base/novnc/package.json').version") != "${novnc_tag#v}" ]]; then
        "${fetch[@]}" "https://codeload.github.com/novnc/noVNC/tar.gz/refs/tags/$novnc_tag" -o novnc.tar.gz
        mkdir novnc
        tar -xzf novnc.tar.gz --strip-components=1 -C novnc
        cp "$base/web-desktop/index.html" novnc/index.html
        "${sync_files[@]}" --delete-delay --exclude='/package.json' novnc/ "$base/novnc/"
        "${sync_files[@]}" novnc/package.json "$base/novnc/"
    fi
}

update_ai_clis() {
    local packages=()
    if command -v codex >/dev/null; then packages+=(@openai/codex@latest); fi
    if command -v claude >/dev/null; then packages+=(@anthropic-ai/claude-code@latest); fi
    if (( ${#packages[@]} == 0 )); then return; fi
    npm install --global --prefix "$cli_prefix" --include=optional --no-audit --no-fund \
        "${packages[@]}"
}

update_mcp() {
    mkdir mcp
    cp "$base/mcp"/package{,-lock}.json mcp/
    node -p "Object.keys(require('$base/mcp/package.json').dependencies).map(name => name + '@latest').join('\n')" > mcp-packages
    mapfile -t packages < mcp-packages
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 PUPPETEER_SKIP_DOWNLOAD=true \
        npm install --prefix "$work/mcp" --save-exact --include=optional --no-audit --no-fund "${packages[@]}"
    "${sync_files[@]}" --delete-delay mcp/node_modules/ "$base/mcp/node_modules/"
    "${sync_files[@]}" mcp/package{,-lock}.json "$base/mcp/"

    # Some ARM images use Playwright's Chromium instead of a distribution package.
    if [[ -d "$base/browsers" && ! -L /usr/bin/google-chrome-stable ]] &&
            grep -Fq "$base/browsers/" /usr/bin/google-chrome-stable; then
        browser_env=(PLAYWRIGHT_BROWSERS_PATH="$base/browsers" PLAYWRIGHT_SKIP_BROWSER_GC=1)
        "${admin[@]}" "${browser_env[@]}" node "$base/mcp/node_modules/playwright/cli.js" install --with-deps chromium
        browser=$(env "${browser_env[@]}" node -p "require('$base/mcp/node_modules/playwright').chromium.executablePath()")
        printf '#!/bin/sh\nexec "%s" "$@"\n' "$browser" > google-chrome-stable
        "${admin[@]}" install -m 755 google-chrome-stable /usr/bin/google-chrome-stable
    fi
}

run_update() {
    local label=$1 status
    shift
    printf '\nUpdating %s...\n' "$label"
    run_action "$@"
    status=$action_status
    if (( status != 0 )); then
        failed+=("$label")
        printf 'Update failed for %s.\n' "$label" >&2
    fi
}

update_software() (
    if [[ $(id -u) == 0 ]]; then
        echo 'Run software updates as the workstation desktop user.' >&2
        exit 1
    fi
    cd "$base"
    failed=()
    mkdir -p "$cli_prefix"
    exec 9<"$cli_prefix"
    flock -n 9 || { echo 'Another workstation update is running.' >&2; exit 1; }

    work=$(mktemp -d)
    trap 'rm -rf -- "$work"' EXIT
    cd "$work"
    sudo -v
    case $(dpkg --print-architecture) in
        amd64) node_arch=x64; uv_arch=x86_64 ;;
        arm64) node_arch=arm64; uv_arch=aarch64 ;;
        *) echo 'Unsupported workstation architecture.' >&2; exit 1 ;;
    esac
    run_update 'system packages, Chrome or Chromium, VS Code, and Claude Desktop' update_apt
    command -v node >/dev/null && run_update 'Node.js, npm, and npx (current Node.js major)' update_node
    run_update 'Codex CLI and Claude Code CLI' update_ai_clis
    [[ -f $base/mcp/package.json ]] && run_update 'workstation MCP packages' update_mcp
    command -v uv >/dev/null && run_update 'uv, uvx, and user-installed uv tools' update_uv
    [[ -f $base/novnc/package.json ]] && run_update 'noVNC' update_novnc
    command -v code >/dev/null && run_update 'VS Code extensions' code --update-extensions
    if (( ${#failed[@]} )); then
        printf '\nCould not finish these updates:\n' >&2
        printf '  %s\n' "${failed[@]}" >&2
        exit 1
    fi
    echo 'Workstation update complete. Reopen applications to use their updated versions.'
)

orca_home=$HOME
if [[ $(id -u) == 0 ]]; then orca_home=$(getent passwd dev | cut -d: -f6); fi
orca_root="$orca_home/.local/share/orca-server"

lock_orca() {
    if ! orca_installed; then echo 'Orca Server is not installed for the workstation user.' >&2; return 1; fi
    exec 8<"$orca_root"
    flock -n 8 || { echo 'Another Orca maintenance action is running.' >&2; return 1; }
}

orca_installed() {
    [[ -L "$orca_root/current" && -x "$orca_root/current/bin/orca-ide" ]]
}

orca_service_state() {
    local status
    status=$(sudo supervisorctl status orca) || :
    case "$status" in
        "orca "*)
            printf '%s\n' "$status" | awk '{print $2}' ;;
        *) echo 'The Orca Supervisor service is unavailable.' >&2; return 1 ;;
    esac
}

restart_orca() (
    lock_orca
    state=$(orca_service_state)
    case "$state" in
        RUNNING) sudo supervisorctl restart orca ;;
        STOPPED|EXITED|FATAL) sudo supervisorctl start orca ;;
        *) echo "Orca is $state. Retry once the service has settled." >&2; exit 1 ;;
    esac
)

select_orca_release() {
    ln -s "$1" "$orca_stage/current"
    mv -Tf "$orca_stage/current" "$orca_root/current"
}

update_orca() (
    set -e
    lock_orca
    state=$(orca_service_state)
    case "$state" in
        RUNNING|STOPPED|EXITED|FATAL) ;;
        *) echo "Orca is $state. Retry once the service has settled." >&2; exit 1 ;;
    esac
    case $(uname -m) in
        x86_64) arch=x64 ;;
        aarch64) arch=arm64 ;;
        *) echo 'Unsupported Orca Server architecture.' >&2; exit 1 ;;
    esac
    tag=$(latest_tag stablyai/orca)
    archive="orca-server-linux-$arch.tar.gz"
    release="$orca_root/releases/orca-server-${tag#v}-linux-$arch"
    previous=$(readlink -f "$orca_root/current")
    if [[ "$previous" == "$release" ]]; then
        echo "Orca Server $tag is already installed."
        exit 0
    fi
    orca_stage=$(mktemp -d "$orca_root/releases/.niu-XXXXXXXX")
    trap 'rm -rf -- "$orca_stage"' EXIT
    cd "$orca_stage"
    if [[ ! -x "$release/bin/orca-ide" ]]; then
        url="https://github.com/stablyai/orca/releases/download/$tag"
        "${fetch[@]}" "$url/$archive" -o "$archive"
        "${fetch[@]}" "$url/orca-server-sha256sums.txt" -o checksums
        awk -v file="$archive" '$2 == file || $2 == "*" file {print}' checksums | sha256sum --check --status
        mkdir unpacked
        tar -xzf "$archive" --strip-components=1 --no-same-owner -C unpacked
        test -x unpacked/bin/orca-ide
        mv -T unpacked "$release"
    fi
    select_orca_release "$release"
    if [[ "$state" == RUNNING ]]; then
        if ! sudo supervisorctl restart orca; then
            echo 'Orca failed to restart. Restoring the previous release.' >&2
            select_orca_release "$previous"
            sudo supervisorctl restart orca
            exit 1
        fi
    fi
    echo "Installed Orca Server $tag."
)

update_self() (
    set -e
    local download destination temporary
    download=$(mktemp -d)
    trap 'rm -rf -- "$download"' EXIT
    destination=$(readlink -f -- "${BASH_SOURCE[0]}")
    "${fetch[@]}" 'https://api.github.com/repos/crazyniu/ai-workstation/contents/workstation/desktop/niu.sh?ref=main' -o "$download/response.json"
    python3 - "$download/response.json" "$download/niu.sh" <<'GITHUB_BLOB'
import base64
import hashlib
import json
from pathlib import Path
import sys

metadata = json.loads(Path(sys.argv[1]).read_bytes())
data = base64.b64decode(metadata["content"])
digest = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
if digest != metadata["sha"] or not data.startswith(b"#!/usr/bin/env bash\n"):
    sys.exit("Invalid niu.sh download from GitHub.")
Path(sys.argv[2]).write_bytes(data)
GITHUB_BLOB
    bash -n "$download/niu.sh"
    if cmp -s "$destination" "$download/niu.sh"; then
        echo 'niu.sh is already up to date.'
        exit 0
    fi
    writer=()
    if [[ ! -w "$(dirname "$destination")" ]]; then writer=(sudo); fi
    temporary=$("${writer[@]}" mktemp -- "${destination}.XXXXXXXX")
    "${writer[@]}" install -m 755 "$download/niu.sh" "$temporary"
    "${writer[@]}" mv -Tf -- "$temporary" "$destination"
    echo 'Updated niu.sh from GitHub main. Reloading the menu.'
)

reset_claude() {
    local python=(python3)
    if [[ $(id -u) == 0 ]]; then
        python=(runuser -u dev -- env HOME="$orca_home" python3)
    fi
    "${python[@]}" - "$@" <<'CLAUDE_RESET_PY'
"""Reset local Claude Code identity while preserving MCP and shared tooling.

Reference: liseami/CCBaga bdfb90ceadfc5fae6772ffff597bddecb0b73cc3,
cleaner_config.rs and cleaner_targets.rs (MIT). Linux adaptation.
Preview first. Close Claude Code before confirming cleanup in the menu.
No new credential backups are created. Actual project directories are untouched.
"""
# MIT License
#
# Copyright (c) 2026 CCBaga contributors
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#

import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import stat
import sys
import tempfile

ACCOUNT_KEYS = set('''
userID machineID anonymousId oauthAccount primaryApiKey additionalModelCostsCache
additionalModelOptionsAnsweredAt additionalModelOptionsCache agentLastUsed
announcementImpressions autoCompactWindowsCache cachedArtifactRoster
cachedChromeExtensionInstalled cachedDynamicConfigs cachedExperimentData
cachedExperimentFeatures cachedExtraUsageDisabledReason cachedGrowthBookFeatures
cachedGrowthBookFeaturesAt cachedStatsigGates cachedUsageUtilization changelogLastFetched
claudeAiMcpEverConnected claudeCodeFirstTokenDate clientDataCache clientDataCacheSlots
closedIssuesLastChecked customApiKeyResponses feedbackSurveyState firstStartTime
firstStartVersion githubWebConnectionStatusCache groveConfigCache hasAvailableSubscription
hasCompletedOnboarding hasOpenedAgentsView hasResetAutoModeOptInForDefaultOffer
hasSeenAutoDefaultNotice hasSeenAutoModeOutsideReadPrompt lastClawdEntranceVersion
lastOnboardingVersion lastPlanModeUse lastReleaseNotesSeen metricsStatusCache
metricsStatusCacheByPrincipal migrationVersion modelAccessCache numStartups
officialMarketplaceAutoInstallAttempted officialMarketplaceAutoInstalled
opusProMigrationComplete orgModelDefaultCache passesEligibilityCache pluginUsage
pluginUsageLspGraceAppliedIds promptQueueUseCount remoteControlUpsellSeenCount
s1mAccessCache seenNotifications skillUsage sonnet1m45MigrationComplete
subscriptionNoticeCount tipLifetimeShownCounts tipsHistory tipsHistoryByCommand
transcriptShareDismissed
'''.split())
CREDENTIAL_KEYS = {'claudeAiOauth', 'trustedDeviceToken'}
AUTH_ENV = {'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN',
            'CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR', 'ANTHROPIC_API_KEY_FILE_DESCRIPTOR'}
RESIDUE = '''projects sessions history.jsonl file-history debug plans image-cache
uploads session-env tasks shell-snapshots feedback-bundles feedback/drafts dev-mods
jobs cache telemetry statsig stats-cache.json todos usage-data usage.jsonl usage.with-fix.jsonl
paste-cache ide daemon daemon.log daemon.status.json .user-id .machine-id backups'''.split()
SHELLS = ['.profile', '.bashrc', '.bash_profile', '.bash_login', '.zshrc', '.zprofile',
          '.zshenv', '.pam_environment']


def safe(home, path):
    path = Path(path)
    if ".." in path.parts:
        raise ValueError("Parent traversal refused: " + str(path))
    path.relative_to(home)
    current = path
    while current != home:
        if current.is_symlink():
            raise ValueError('Symlink target refused: ' + str(current))
        current = current.parent
    return path


def read_json(path):
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('JSON too large: ' + str(path))
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('Expected JSON object: ' + str(path))
    return value


def clean_account(value):
    result = {k: v for k, v in value.items() if k not in ACCOUNT_KEYS}
    # Project entries contain personal sessions/usage. Keep only MCP settings.
    if 'projects' in result:
        if not isinstance(result['projects'], dict):
            raise ValueError('projects must be an object')
        projects = {}
        for name, entry in result['projects'].items():
            if not isinstance(entry, dict):
                raise ValueError('project settings must be objects')
            mcp = {k: v for k, v in entry.items() if 'mcp' in k.lower()}
            if mcp:
                projects[name] = mcp
        if projects:
            result['projects'] = projects
        else:
            result.pop('projects')
    return result


def clean_settings(value):
    result = dict(value)
    if 'env' in result:
        if not isinstance(result['env'], dict):
            raise ValueError('settings env must be an object')
        result['env'] = {k: v for k, v in result['env'].items() if k not in AUTH_ENV}
    result.pop('apiKeyHelper', None)
    return result


def clean_shell(text):
    lines = []
    for line in text.splitlines(keepends=True):
        match = re.match(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=', line)
        if match and match[1] in AUTH_ENV:
            # A complex command could mix credentials with unrelated actions.
            # Refuse the whole plan instead of executing or partially editing it.
            raw = line[match.end():].strip()
            if (any(c in raw for c in ';`$\n&|<>')
                    or len(shlex.split(raw, comments=True)) > 1):
                raise ValueError('Complex auth assignment requires manual review')
            continue
        lines.append(line)
    return ''.join(lines)


def plan(home, config):
    changes, removals = [], []
    configs = [(home / '.claude.json', clean_account),
               (config / '.claude.json', clean_account),
               (config / '.credentials.json', lambda v: {k: x for k, x in v.items() if k not in CREDENTIAL_KEYS}),
               (config / 'settings.json', clean_settings),
               (config / 'settings.local.json', clean_settings)]
    visited = set()
    for path, transform in configs:
        safe(home, path)
        if path in visited or not path.exists():
            continue
        visited.add(path)
        before = read_json(path)
        after = transform(before)
        if before != after:
            changes.append((path, (json.dumps(after, indent=2, ensure_ascii=False)+'\n').encode()))
    for name in SHELLS:
        path = safe(home, home/name)
        if path.exists():
            before = path.read_text()
            after = clean_shell(before)
            if before != after:
                changes.append((path, after.encode()))
    candidates = [config/name for name in RESIDUE]
    candidates += [home/'.cache/claude-cli-nodejs']
    candidates += list(home.glob('.claude.json.backup*'))
    candidates += list(config.glob('.claude.json.backup*'))
    for path in candidates:
        safe(home, path)
        if path.exists() and path not in removals:
            # Only regular files/directories within the selected HOME.
            if not (path.is_file() or path.is_dir()):
                raise ValueError('Unsupported file type: ' + str(path))
            removals.append(path)
    return changes, removals


def active_claude(uid):
    for p in Path('/proc').iterdir():
        if not p.name.isdigit() or int(p.name) == os.getpid():
            continue
        try:
            if p.stat().st_uid != uid:
                continue
            comm = (p/'comm').read_text().strip().lower()
            if comm == 'claude':
                return True
            args = (p/'cmdline').read_bytes().split(b'\0')
            names = [Path(os.fsdecode(a)).name for a in args[:3] if a]
            if any(n in {'claude', 'claude.exe', 'claude.js'} for n in names):
                return True
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    return False


def atomic_write(path, data):
    old = path.stat()
    fd, temp = tempfile.mkstemp(prefix='.claude-reset-', dir=path.parent)
    try:
        os.fchmod(fd, stat.S_IMODE(old.st_mode) & 0o600)
        os.fchown(fd, old.st_uid, old.st_gid)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main(home, apply):
    home = home.absolute()
    if '..' in home.parts or home.is_symlink() or not home.is_dir() or home.resolve() == Path('/'):
        raise ValueError('Expected a real user HOME directory')
    home = home.resolve()
    uid = home.stat().st_uid
    if os.getuid() not in (0, uid):
        raise ValueError('Run as the target user or root')
    config = Path(os.environ.get('CLAUDE_CONFIG_DIR') or str(home/'.claude'))
    if not config.is_absolute() or config == home:
        raise ValueError('CLAUDE_CONFIG_DIR must be a dedicated absolute directory inside HOME')
    safe(home, config)
    # Lock the HOME directory itself; do not create a permanent lock or backup.
    fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if apply and active_claude(uid):
            raise ValueError('Close all Claude Code processes before applying')
        if apply and AUTH_ENV.intersection(os.environ):
            raise ValueError('Unset inherited Claude auth variables first: ' + ', '.join(sorted(AUTH_ENV.intersection(os.environ))))
        changes, removals = plan(home, config)
        print('APPLY' if apply else 'PREVIEW (no changes)')
        for path, _ in changes:
            print('sanitize', path.relative_to(home))
        for path in removals:
            print('remove', path.relative_to(home))
        if apply:
            for path, data in changes:
                if active_claude(uid):
                    raise ValueError('Claude restarted; stopped after partial cleanup')
                safe(home, path)
                atomic_write(path, data)
            for path in removals:
                if active_claude(uid):
                    raise ValueError('Claude restarted; stopped after partial cleanup')
                safe(home, path)
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
        print(f'{len(changes)} config edits, {len(removals)} residue paths. MCP, plugins, skills, proxy settings and actual project files are preserved.')
        print('Scope: local Claude Code files in this HOME. Browser logins, remote sessions and shell history are separate.')
    finally:
        os.close(fd)


if __name__ == '__main__':
    try:
        main(Path.home(), sys.argv[1:] == ['apply'])
    except (OSError, ValueError) as error:
        print('Refused: '+str(error), file=sys.stderr)
        sys.exit(1)
CLAUDE_RESET_PY
}

confirm_action() {
    local answer
    printf '%s\n  1. Confirm\n  0. Cancel\n' "$1"
    while read -rp 'Choose 1 or 0: ' answer; do
        case "$answer" in
            1) return 0 ;;
            0) return 1 ;;
        esac
    done
    return 1
}

run_action() {
    set +e
    (set -e; "$@")
    action_status=$?
    set -e
    if (( action_status != 0 )); then
        printf 'Action did not complete (exit %d).\n' "$action_status" >&2
    fi
}

menu() {
    local choice action_status
    while true; do
        printf '\nniu.sh\n  1. Update installed software\n'
        if orca_installed; then
            printf '  2. Update Orca Server\n  3. Restart Orca Server\n'
        fi
        printf '  4. Update niu.sh from GitHub\n  5. Reset Claude Code user data\n  0. Exit\n'
        read -rp 'Choose a number: ' choice || return 0
        case "$choice" in
            0) return 0 ;;
            1) confirm_action 'Update installed workstation software?' || continue
               run_action update_software ;;
            2|3)
                if ! orca_installed; then echo 'Orca Server is not installed.'; continue; fi
                if [[ "$choice" == 2 ]]; then
                    confirm_action 'Update Orca Server? Active sessions may disconnect.' || continue
                    run_action update_orca
                else
                    confirm_action 'Restart Orca Server? Active sessions will disconnect.' || continue
                    run_action restart_orca
                fi ;;
            4) confirm_action 'Update this script from GitHub main?' || continue
               run_action update_self
               if (( action_status == 0 )); then exec "$self"; fi ;;
            5) run_action reset_claude
               if (( action_status != 0 )); then continue; fi
               confirm_action 'Permanently apply the Claude cleanup shown above?' || continue
               run_action reset_claude apply ;;
            *) echo 'Choose one of the listed numbers.' ;;
        esac
    done
}

self=$(readlink -f -- "${BASH_SOURCE[0]}")
if (( $# )); then
    echo 'Open niu.sh without arguments and choose a menu number.' >&2
    exit 2
fi
if [[ ! -t 0 && /dev/stdin -ef /dev/null && -n ${DISPLAY:-} ]]; then
    exec xfce4-terminal --execute "$self"
fi
menu
