#!/usr/bin/env bash
# Run during the image build as root; downloads only public, pinned artifacts.
set -euo pipefail
base=/opt/workstation
source "$base/versions.env"
[[ $(uname -m) == x86_64 ]] || { echo 'This image supports linux/amd64 only.' >&2; exit 1; }
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

download "codex-$CODEX_VERSION.tar.gz" \
    "https://github.com/openai/codex/releases/download/rust-v$CODEX_VERSION/codex-package-x86_64-unknown-linux-musl.tar.gz" "$CODEX_SHA256"
install -d "$base/codex/$CODEX_VERSION"
tar -xzf "$stage/codex-$CODEX_VERSION.tar.gz" -C "$base/codex/$CODEX_VERSION"

download "claude-$CLAUDE_VERSION.zst" \
    "https://downloads.claude.ai/claude-code-releases/$CLAUDE_VERSION/linux-x64/claude.zst" "$CLAUDE_ZSTD_SHA256"
install -d "$base/claude"
zstd --decompress --stdout "$stage/claude-$CLAUDE_VERSION.zst" > "$base/claude/claude-$CLAUDE_VERSION"
printf '%s  %s\n' "$CLAUDE_SHA256" "$base/claude/claude-$CLAUDE_VERSION" | sha256sum --check --status
chmod 755 "$base/claude/claude-$CLAUDE_VERSION"

download "godot-$GODOT_VERSION.zip" \
    "https://github.com/godotengine/godot-builds/releases/download/$GODOT_VERSION-stable/Godot_v$GODOT_VERSION-stable_linux.x86_64.zip" "$GODOT_SHA256"
unzip -q "$stage/godot-$GODOT_VERSION.zip" -d "$stage/godot"
install -d "$base/godot"
install -m 755 "$stage/godot/Godot_v$GODOT_VERSION-stable_linux.x86_64" "$base/godot/godot-$GODOT_VERSION"

# Keep the complete Codex bundle: helpers and resources resolve relative to bin/codex.
# Every interactive launcher refuses root and retains no_new_privs for its children.
for name in codex claude godot; do
    case "$name" in
        codex) target="$base/codex/$CODEX_VERSION/bin/codex"; extra='' ;;
        claude) target="$base/claude/claude-$CLAUDE_VERSION"; extra='' ;;
        godot) target="$base/godot/godot-$GODOT_VERSION"; extra='--rendering-method gl_compatibility' ;;
    esac
    cat > "/usr/local/bin/$name" <<SH
#!/bin/sh
set -eu
if [ "\$(id -u)" -eq 0 ]; then
    echo 'Run $name as the dev account.' >&2
    exit 1
fi
exec /usr/bin/setpriv --no-new-privs '$target' $extra "\$@"
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
base=/opt/workstation/mcp/node_modules
case "${1:-}" in
    context7) script="$base/@upstash/context7-mcp/dist/index.js" ;;
    playwright) script="$base/@playwright/mcp/cli.js" ;;
    chrome-devtools) script="$base/chrome-devtools-mcp/build/src/bin/chrome-devtools-mcp.js" ;;
    godot) script="$base/@coding-solo/godot-mcp/build/index.js" ;;
    *) echo 'Choose context7, playwright, chrome-devtools, or godot.' >&2; exit 2 ;;
esac
shift
exec /usr/bin/setpriv --no-new-privs /usr/local/bin/node "$script" "$@"
SH
chmod 755 /usr/local/bin/workstation-mcp
python3 "$base/scripts/configure-mcp.py" --home "$base/home-template"
chown -R root:root "$base"
chmod -R go-w "$base"
echo 'Pinned tools and credential-free MCP templates installed.'
