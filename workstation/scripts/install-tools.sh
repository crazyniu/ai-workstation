#!/usr/bin/env bash
# Run during the image build as root; downloads only public, pinned artifacts.
set -euo pipefail
base=/opt/workstation
source "$base/versions.env"
case $(dpkg --print-architecture) in
    amd64) triple=x86_64; claude_arch=x64 ;;
    arm64) triple=aarch64; claude_arch=arm64
        CODEX_SHA256=$CODEX_ARM64_SHA256
        CLAUDE_ZSTD_SHA256=$CLAUDE_ARM64_ZSTD_SHA256
        CLAUDE_SHA256=$CLAUDE_ARM64_SHA256
        UV_SHA256=$UV_ARM64_SHA256 ;;
    *) echo 'Codex and Claude upstream Linux binaries require amd64 or arm64.' >&2; exit 1 ;;
esac
[[ $(node --version) == "v$NODE_VERSION" ]] || { echo 'Unexpected Node.js version.' >&2; exit 1; }
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT

download() {
    local filename=$1 url=$2 expected=$3
    if [[ -n ${WORKSTATION_DOWNLOAD_CACHE:-} && -f $WORKSTATION_DOWNLOAD_CACHE/$filename ]]; then
        cp "$WORKSTATION_DOWNLOAD_CACHE/$filename" "$stage/$filename"
    else
        curl --fail --location --retry 5 --retry-all-errors --connect-timeout 30 \
            --max-time 1200 "$url" --output "$stage/$filename"
    fi
    printf '%s  %s\n' "$expected" "$stage/$filename" | sha256sum --check --status
}

download "codex-$CODEX_VERSION-$triple.tar.gz" \
    "https://github.com/openai/codex/releases/download/rust-v$CODEX_VERSION/codex-package-$triple-unknown-linux-musl.tar.gz" "$CODEX_SHA256"
install -d "$base/codex/$CODEX_VERSION"
tar -xzf "$stage/codex-$CODEX_VERSION-$triple.tar.gz" -C "$base/codex/$CODEX_VERSION"

download "claude-$CLAUDE_VERSION-$claude_arch.zst" \
    "https://downloads.claude.ai/claude-code-releases/$CLAUDE_VERSION/linux-$claude_arch/claude.zst" "$CLAUDE_ZSTD_SHA256"
install -d "$base/claude"
zstd --decompress --stdout "$stage/claude-$CLAUDE_VERSION-$claude_arch.zst" > "$base/claude/claude-$CLAUDE_VERSION"
printf '%s  %s\n' "$CLAUDE_SHA256" "$base/claude/claude-$CLAUDE_VERSION" | sha256sum --check --status
chmod 755 "$base/claude/claude-$CLAUDE_VERSION"

download "uv-$UV_VERSION-$triple.tar.gz" \
    "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-$triple-unknown-linux-gnu.tar.gz" "$UV_SHA256"
tar -xzf "$stage/uv-$UV_VERSION-$triple.tar.gz" -C "$stage"
install -m 755 "$stage/uv-$triple-unknown-linux-gnu"/{uv,uvx} /usr/local/bin/

# Keep the complete Codex bundle: helpers and resources resolve relative to bin/codex.
# Desktop and shell launchers both select the dev user's updated CLI.
for name in codex claude; do
    case "$name" in
        codex) target="$base/codex/$CODEX_VERSION/bin/codex" ;;
        claude) target="$base/claude/claude-$CLAUDE_VERSION" ;;
    esac
    cat > "/usr/local/bin/$name" <<SH
#!/bin/sh
set -eu
if [ "\$(id -u)" -eq 0 ]; then
    echo 'Run $name as the dev account.' >&2
    exit 1
fi
updated="\$HOME/.local/share/workstation-cli/bin/$name"
target='$target'
if [ -x "\$updated" ]; then
    target="\$updated"
fi
exec "\$target" "\$@"
SH
    chmod 755 "/usr/local/bin/$name"
done

cd "$base/mcp"
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 PUPPETEER_SKIP_DOWNLOAD=true npm ci --omit=dev --no-audit --no-fund
npm cache clean --force
cat > /usr/local/bin/workstation-mcp <<'SH'
#!/bin/sh
set -eu
if [ "$(id -u)" -eq 0 ]; then
    echo 'Run MCP servers as the dev account.' >&2
    exit 1
fi
case "${1:-}" in
    context7|playwright|chrome-devtools) command="/opt/workstation/mcp/node_modules/.bin/$1-mcp" ;;
    *) echo 'Choose context7, playwright, or chrome-devtools.' >&2; exit 2 ;;
esac
shift
exec /usr/bin/setpriv --no-new-privs "$command" "$@"
SH
chmod 755 /usr/local/bin/workstation-mcp
python3 "$base/scripts/configure-mcp.py" --home "$base/home-template"
chown -R root:root "$base"
chmod -R go-w "$base"
echo 'Pinned tools and credential-free MCP templates installed.'
