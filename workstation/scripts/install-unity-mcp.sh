#!/usr/bin/env bash
# Install the open-source bridge only; no Unity account or Editor license.
set -euo pipefail
base=/opt/workstation
source "$base/unity/versions.env"
[[ $(id -u) -eq 0 && $(uname -m) == x86_64 ]] || { echo 'Run as root on Linux amd64.' >&2; exit 1; }
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
curl -fsSL --retry 4 --connect-timeout 30 --max-time 300 \
    "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-x86_64-unknown-linux-gnu.tar.gz" -o "$stage/uv.tar.gz"
printf '%s  %s\n' "$UV_SHA256" "$stage/uv.tar.gz" | sha256sum --check --status
tar -xzf "$stage/uv.tar.gz" -C "$stage"
install -m 755 "$stage/uv-x86_64-unknown-linux-gnu/uv" "$stage/uv-x86_64-unknown-linux-gnu/uvx" /usr/local/bin/
UV_PYTHON_DOWNLOADS=never uv venv --python /usr/bin/python3 "$base/unity-mcp"
UV_NO_CACHE=1 uv pip install --python "$base/unity-mcp/bin/python" --require-hashes -r "$base/unity/requirements.lock"
curl -fsSL --retry 4 --connect-timeout 30 --max-time 300 \
    "https://codeload.github.com/CoplayDev/unity-mcp/tar.gz/$UNITY_MCP_COMMIT" -o "$stage/bridge.tar.gz"
printf '%s  %s\n' "$UNITY_MCP_SOURCE_SHA256" "$stage/bridge.tar.gz" | sha256sum --check --status
tar -xzf "$stage/bridge.tar.gz" -C "$stage" \
    "unity-mcp-$UNITY_MCP_COMMIT/MCPForUnity" "unity-mcp-$UNITY_MCP_COMMIT/LICENSE"
cp -a "$stage/unity-mcp-$UNITY_MCP_COMMIT/MCPForUnity" "$base/unity/"
install -m 644 "$stage/unity-mcp-$UNITY_MCP_COMMIT/LICENSE" "$base/unity/UPSTREAM-LICENSE"
install -m 755 "$base/scripts/unity-mcp" /usr/local/bin/unity-mcp
chown -R root:root "$base/unity-mcp" "$base/unity"
chmod -R go-w "$base/unity-mcp" "$base/unity"
