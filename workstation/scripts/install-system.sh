#!/usr/bin/env bash
# Shared package provisioning for a clean image or a preflighted native host.
set -euo pipefail
source /opt/workstation/versions.env
arch=$(dpkg --print-architecture)
if [[ $(dpkg --print-architecture) == arm64 ]]; then VSCODE_VERSION=$VSCODE_ARM64_VERSION; fi
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg python3 python3-tomlkit git gh locales tzdata supervisor openssh-server \
    util-linux procps iproute2 tar unzip xz-utils zstd gcc libc6-dev \
    xfce4-session xfwm4 xfce4-panel xfdesktop4 xfce4-settings xfce4-terminal thunar dbus-x11 \
    tigervnc-standalone-server tigervnc-tools x11-utils x11-xserver-utils \
    arc-theme papirus-icon-theme fonts-inter fonts-noto-cjk fonts-dejavu-core \
    libgl1-mesa-dri libgl1 libegl1 mesa-utils xdg-utils websockify openssl xclip
# Debian/older Ubuntu provide the SVG pixbuf loader separately. Newer systems
# may provide it through glycin; retain that system's loader in that case.
if apt-cache show librsvg2-common >/dev/null 2>&1; then
    apt-get install -y --no-install-recommends librsvg2-common
fi
localedef -i en_SG -f UTF-8 en_SG.UTF-8
useradd --uid 1100 --user-group --create-home --shell /bin/bash dev
if [[ ${WORKSTATION_INSTALL_MODE:-container} == container ]]; then
    apt-get install -y --no-install-recommends sudo
    usermod -aG sudo dev
    passwd --lock root
    passwd --lock dev
    chmod 700 /root
    rm -f /etc/ssh/ssh_host_*
fi
curl -fsSL --retry 4 https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/workstation-vscode.gpg
printf 'deb [arch=%s signed-by=/usr/share/keyrings/workstation-vscode.gpg] https://packages.microsoft.com/repos/code stable main\n' "$arch" > /etc/apt/sources.list.d/workstation-vscode.list
if [[ $arch == amd64 ]]; then
    curl -fsSL --retry 4 https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/workstation-chrome.gpg
    echo 'deb [arch=amd64 signed-by=/usr/share/keyrings/workstation-chrome.gpg] https://dl.google.com/linux/chrome/deb/ stable main' > /etc/apt/sources.list.d/workstation-chrome.list
    apt-get update
    apt-get install -y --no-install-recommends "google-chrome-stable=$CHROME_VERSION" "code=$VSCODE_VERSION"
else
    # Google does not publish Chrome for Linux ARM64. Debian Chromium uses
    # the same sandbox, DevTools protocol and MCP executable contract.
    apt-get update
    apt-get install -y --no-install-recommends "code=$VSCODE_VERSION"
    source /etc/os-release
    if [[ $ID == debian ]]; then
        apt-get install -y --no-install-recommends chromium
        ln -s /usr/bin/chromium /usr/bin/google-chrome-stable
    fi
    sed -i 's/Name=Google Chrome/Name=Chromium/; s/Icon=google-chrome/Icon=chromium/' /opt/workstation/home-template/Desktop/google-chrome.desktop
fi
if [[ ${WORKSTATION_INSTALL_MODE:-container} == container ]]; then
    repo=https://downloads.claude.ai/claude-desktop
    key=/usr/share/keyrings/claude-desktop-archive-keyring.asc
    curl -fsSLo "$key" "$repo/key.asc"
    printf '%s  %s\n' "$CLAUDE_DESKTOP_KEY_SHA256" "$key" | sha256sum --check --status
    printf 'deb [arch=%s signed-by=%s] %s/apt/stable stable main\n' "$arch" "$key" "$repo" \
        > /etc/apt/sources.list.d/claude-desktop.list
    apt-get update
    stage=$(mktemp -d)
    trap 'rm -rf "$stage"' EXIT
    package="claude-desktop_${CLAUDE_DESKTOP_VERSION}_${arch}.deb"
    (cd "$stage" && apt-get download "claude-desktop=$CLAUDE_DESKTOP_VERSION")
    digest=$CLAUDE_DESKTOP_AMD64_SHA256
    if [[ $arch == arm64 ]]; then digest=$CLAUDE_DESKTOP_ARM64_SHA256; fi
    printf '%s  %s\n' "$digest" "$stage/$package" | sha256sum --check --status
    apt-get install -y --no-install-recommends "$stage/$package" gnome-keyring libayatana-appindicator3-1 libglib2.0-bin
    rm -rf /var/lib/apt/lists/*
fi
