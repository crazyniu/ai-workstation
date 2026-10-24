#!/usr/bin/env bash
set -euo pipefail
source /opt/workstation/web-desktop/versions.env
archive=$(mktemp)
trap 'rm -f "$archive"' EXIT
curl -fsSL --retry 4 "https://codeload.github.com/novnc/noVNC/tar.gz/refs/tags/v${NOVNC_VERSION}" -o "$archive"
printf '%s  %s\n' "$NOVNC_SHA256" "$archive" | sha256sum -c -
install -d /opt/workstation/novnc
tar -xzf "$archive" --strip-components=1 -C /opt/workstation/novnc
install -m 644 /opt/workstation/web-desktop/index.html /opt/workstation/novnc/index.html
chmod -R go-w /opt/workstation/novnc
