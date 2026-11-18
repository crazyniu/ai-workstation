#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C.UTF-8 LANGUAGE=en

if [[ ! -t 0 && -n ${DISPLAY:-} ]]; then
    exec xfce4-terminal --hold --execute "$0"
fi
if [[ $(id -u) == 0 ]]; then
    echo 'Run this updater as the workstation desktop user.' >&2
    exit 1
fi

base=/opt/workstation
cd "$base"
cli_prefix="$HOME/.local/share/workstation-cli"
mkdir -p "$cli_prefix"
exec 9<"$cli_prefix"
flock -n 9 || { echo 'Another workstation update is running.' >&2; exit 1; }

work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
cd "$work"
sudo -v
admin=(sudo -H --preserve-env=http_proxy,https_proxy,no_proxy,HTTP_PROXY,HTTPS_PROXY,NO_PROXY env LC_ALL=C.UTF-8 LANGUAGE=en)
apt=("${admin[@]}" DEBIAN_FRONTEND=noninteractive apt-get -o Dpkg::Options::=--force-confold)
fetch=(curl --fail --location --silent --show-error --retry 3)

# Replace files by rename so running binaries remain usable during the update.
sync_files=("${admin[@]}" rsync -a --checksum --chown=root:root --chmod=a+rX,go-w --delay-updates)

case $(dpkg --print-architecture) in
    amd64) node_arch=x64; uv_arch=x86_64 ;;
    arm64) node_arch=arm64; uv_arch=aarch64 ;;
    *) echo 'Unsupported workstation architecture.' >&2; exit 1 ;;
esac

latest_tag() {
    "${fetch[@]}" "https://api.github.com/repos/$1/releases/latest" |
        python3 -c 'import json, sys; print(json.load(sys.stdin)["tag_name"])'
}

update_apt() {
    "${apt[@]}" -o APT::Update::Error-Mode=any update
    "${apt[@]}" --with-new-pkgs upgrade -y
    if ! command -v rsync >/dev/null; then
        "${apt[@]}" install -y --no-install-recommends rsync
    fi
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
    npm install --global --prefix "$cli_prefix" --include=optional --no-audit --no-fund \
        @openai/codex@latest @anthropic-ai/claude-code@latest
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

failed=()
run_update() {
    local label=$1 status
    shift
    printf '\nUpdating %s...\n' "$label"
    set +e
    (set -e; "$@")
    status=$?
    set -e
    if (( status != 0 )); then
        failed+=("$label")
        printf 'Update failed for %s (exit %d).\n' "$label" "$status" >&2
    fi
}

run_update 'system packages, Chrome or Chromium, VS Code, and Claude Desktop' update_apt
run_update 'Node.js, npm, and npx (current Node.js major)' update_node
run_update 'Codex CLI and Claude Code CLI' update_ai_clis
run_update 'workstation MCP packages' update_mcp
run_update 'uv, uvx, and user-installed uv tools' update_uv
run_update 'noVNC' update_novnc
run_update 'VS Code extensions' code --update-extensions
if (( ${#failed[@]} )); then
    printf '\nCould not finish these updates:\n' >&2
    printf '  %s\n' "${failed[@]}" >&2
    exit 1
fi
echo 'Workstation update complete. Reopen applications to use their updated versions.'
