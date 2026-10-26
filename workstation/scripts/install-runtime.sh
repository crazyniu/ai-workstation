#!/usr/bin/env bash
set -euo pipefail
base=/opt/workstation
if [[ ! -e /usr/bin/google-chrome-stable ]]; then
    # Ubuntu ARM64 ships a Snap launcher instead of a container-safe Chromium.
    # Use the browser revision pinned by the existing Playwright npm lock.
    export PLAYWRIGHT_BROWSERS_PATH=$base/browsers
    node "$base/mcp/node_modules/playwright/cli.js" install --with-deps chromium
    executable=$(node -e 'process.stdout.write(require("/opt/workstation/mcp/node_modules/playwright").chromium.executablePath())')
    printf '#!/bin/sh\nexec "%s" "$@"\n' "$executable" > /usr/bin/google-chrome-stable
    chmod 755 /usr/bin/google-chrome-stable
fi
install -d /usr/local/libexec/workstation-glycin
# Scoped to the desktop; browser launchers retain their own sandbox.
gcc -O2 -Wall -Wextra "$base/desktop/bwrap-desktop-compat.c" -o /usr/local/libexec/workstation-glycin/bwrap
chmod -R go-w "$base/home-template" "$base/desktop" /usr/local/libexec/workstation-glycin
chmod 755 "$base/home-template"/Desktop/*.desktop
chmod 644 "$base/versions.env" "$base/home-template/.claude.json" "$base/home-template/.codex/config.toml"
install -o 1100 -g 1100 -m 644 "$base/home-template/.profile" /home/dev/.profile
bash "$base/web-desktop/install.sh"
install -m 755 /etc/workstation/entrypoint.py /usr/local/bin/workstation-entrypoint
install -d /etc/supervisor/conf.d
install -m 755 "$base/scripts/configure-exit-dns.py" /usr/local/bin/configure-workstation-exit-dns
install -m 755 "$base/scripts/reset-claude-user.py" /usr/local/bin/reset-claude-user
install -m 755 /etc/workstation/start-desktop /usr/local/bin/workstation-desktop
install -m 755 /etc/workstation/start-vnc /usr/local/bin/workstation-vnc
if [[ ${WORKSTATION_INSTALL_MODE:-container} == container ]]; then
    install -m 644 /etc/workstation/sshd_config /etc/ssh/sshd_config
    install -m 644 /etc/workstation/supervisord.conf /etc/supervisor/supervisord.conf
fi
