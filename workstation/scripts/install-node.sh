#!/usr/bin/env bash
set -euo pipefail
source /opt/workstation/versions.env
case $(dpkg --print-architecture) in
    amd64) arch=x64; digest=$NODE_AMD64_SHA256 ;;
    arm64) arch=arm64; digest=$NODE_ARM64_SHA256 ;;
    *) echo 'No pinned Node runtime for this workstation CPU.' >&2; exit 1 ;;
esac
archive=$(mktemp)
trap 'rm -f "$archive"' EXIT
curl -fsSL --retry 4 "https://nodejs.org/dist/v$NODE_VERSION/node-v$NODE_VERSION-linux-$arch.tar.xz" -o "$archive"
printf '%s  %s\n' "$digest" "$archive" | sha256sum --check --status
install -d /opt/node
tar -xJf "$archive" --strip-components=1 -C /opt/node
for name in node npm npx; do ln -s "/opt/node/bin/$name" "/usr/local/bin/$name"; done
