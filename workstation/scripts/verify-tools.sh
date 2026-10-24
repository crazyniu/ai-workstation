#!/usr/bin/env bash
# Run inside a freshly started container as dev. Does not authenticate AI services.
set -euo pipefail
[[ $(id -u) -ne 0 ]] || { echo 'Run this check as dev.' >&2; exit 1; }
source /opt/workstation/versions.env
source /opt/workstation/unity/versions.env
uv_output=$(uv --version)
printf '%s\n' "$uv_output"
# Official binaries can append build metadata, e.g. (x86_64-unknown-linux-gnu).
[[ $uv_output == "uv $UV_VERSION" || $uv_output == "uv $UV_VERSION ("*")" ]] || {
    echo "Expected uv $UV_VERSION; got: $uv_output" >&2
    exit 1
}
[[ $(/opt/workstation/unity-mcp/bin/python -c 'from importlib.metadata import version; print(version("mcpforunityserver"))') == "$UNITY_MCP_VERSION" ]]
[[ $(node --version) == "v$NODE_VERSION" ]]
codex --version | grep -F "$CODEX_VERSION"
claude --version | grep -F "$CLAUDE_VERSION"
godot --version | grep -F "$GODOT_VERSION"
git --version
gh --version
chrome=$(google-chrome-stable --version)
printf '%s\n' "$chrome"
[[ $chrome == "Google Chrome ${CHROME_VERSION%-*} " || $chrome == "Google Chrome ${CHROME_VERSION%-*}" ]]
code_version=$(code --version)
printf '%s\n' "$code_version"
[[ ${code_version%%$'\n'*} == "${VSCODE_VERSION%-*}" ]]
[[ $(dpkg-query -W -f='${Version}' code) == "$VSCODE_VERSION" ]]
[[ $(dpkg-query -W -f='${Version}' google-chrome-stable) == "$CHROME_VERSION" ]]
node /opt/workstation/scripts/mcp-smoke.mjs "$@"
