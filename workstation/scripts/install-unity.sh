#!/usr/bin/env bash
# Add the official Editor and Hub to an existing workstation, preserving HOME.
# Activation remains an interactive Unity Hub step using the user's own account.
set -euo pipefail
base=/opt/workstation
source "$base/unity/versions.env"
[[ $(id -u) -eq 0 && $(uname -m) == x86_64 ]] || { echo 'Run as root on Linux amd64.' >&2; exit 1; }
cache=${WORKSTATION_UNITY_CACHE_DIR:-/var/tmp/workstation-unity-download}
install -d -m 755 "$cache" /opt/unity
download() {
    local url=$1 file=$2 checksum=$3
    if ! printf '%s  %s\n' "$checksum" "$file" | sha256sum --check --status 2>/dev/null; then
        curl -fL --retry 4 --connect-timeout 30 --max-time 3600 --continue-at - "$url" -o "$file"
        printf '%s  %s\n' "$checksum" "$file" | sha256sum --check --status
    fi
}
if [[ ! -x /opt/unity/$UNITY_EDITOR_VERSION/Editor/Unity ]]; then
    download "$UNITY_EDITOR_URL" "$cache/Unity-$UNITY_EDITOR_VERSION.tar.xz" "$UNITY_EDITOR_SHA256"
    stage=$(mktemp -d /opt/unity/.install-XXXXXXXX)
    trap 'rm -rf "$stage"' EXIT
    tar --no-same-owner -xJf "$cache/Unity-$UNITY_EDITOR_VERSION.tar.xz" -C "$stage"
    test -x "$stage/Editor/Unity"
    chmod 755 "$stage"
    chmod -R go-w "$stage"
    mv "$stage" "/opt/unity/$UNITY_EDITOR_VERSION"
    trap - EXIT
fi
download "$UNITY_HUB_URL" "$cache/unityhub.deb" "$UNITY_HUB_SHA256"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    libglib2.0-bin "$cache/unityhub.deb" libgtk2.0-0t64 libnss3 libasound2t64 libglu1-mesa libxslt1.1
cat > /usr/local/bin/unity-editor <<SH
#!/bin/sh
set -eu
[ "\$(id -u)" -ne 0 ] || { echo 'Run Unity as the desktop user.' >&2; exit 1; }
exec /usr/bin/setpriv --no-new-privs /opt/unity/$UNITY_EDITOR_VERSION/Editor/Unity "\$@"
SH
chmod 755 /usr/local/bin/unity-editor
install -m 644 "$base/unity/unity-editor.desktop" /usr/share/applications/workstation-unity.desktop
if getent passwd dev >/dev/null; then
    desktop_home=$(getent passwd dev | cut -d: -f6)
    runuser -u dev -- env HOME="$desktop_home" python3 - <<'PY'
from pathlib import Path
import shutil
desktop = Path.home() / 'Desktop'
desktop.mkdir(exist_ok=True)
for source, name in [('/usr/share/applications/workstation-unity.desktop', 'Unity Editor.desktop'),
                     ('/usr/share/applications/unityhub.desktop', 'Unity Hub.desktop')]:
    target = desktop / name
    if not target.exists():
        shutil.copyfile(source, target)
        target.chmod(0o755)
PY
fi
echo "Installed Unity $UNITY_EDITOR_VERSION and Hub $UNITY_HUB_VERSION. Activate Unity Personal in the Hub."
