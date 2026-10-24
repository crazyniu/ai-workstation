ARG NODE_BASE=node:24.22.1-bookworm-slim@sha256:2dd9a4f758e173b65fee15388f7706af6fb01ef50cf7a2c0538711d67a6981ae
ARG UBUNTU_BASE=ubuntu:26.04@sha256:42527649dbc4f9197a6073f426f488cbff0e9cc9f2afce32d91c383e4875634a
# Optional public artifact cache supplied with --build-context tool-download-cache=PATH.
# Empty by default; downloads always retain the versions.env SHA256 checks.
FROM scratch AS tool-download-cache
FROM ${NODE_BASE} AS node-runtime
FROM ${UBUNTU_BASE}
ARG DEBIAN_FRONTEND=noninteractive
LABEL org.opencontainers.image.title="AI Workstation" \
      org.opencontainers.image.description="Private, reproducible amd64 XFCE development workstation" \
      org.opencontainers.image.source="https://github.com/crazyniu/ai-workstation"
ENV WORKSTATION_COUNTRY=US WORKSTATION_LANGUAGE=en WORKSTATION_TIMEZONE=America/Los_Angeles \
    TZ=America/Los_Angeles LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 LANGUAGE=en_US:en \
    CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS=1 CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS=1
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN apt-get update && apt-get install -y --no-install-recommends \
       ca-certificates curl gnupg python3 git gh locales tzdata supervisor openssh-server \
       util-linux procps iproute2 tar unzip zstd gcc libc6-dev \
       xfce4-session xfwm4 xfce4-panel xfdesktop4 xfce4-settings xfce4-terminal thunar dbus-x11 \
       tigervnc-standalone-server tigervnc-tools x11-utils x11-xserver-utils \
       arc-theme papirus-icon-theme fonts-inter fonts-noto-cjk fonts-dejavu-core \
       libgl1-mesa-dri libgl1 libegl1 mesa-utils xdg-utils \
    && locale-gen en_US.UTF-8 && ln -snf /usr/share/zoneinfo/America/Los_Angeles /etc/localtime \
    && echo America/Los_Angeles > /etc/timezone \
    && useradd --uid 1100 --user-group --create-home --shell /bin/bash dev \
    && passwd --lock root && passwd --lock dev && chmod 700 /root \
    && rm -f /etc/ssh/ssh_host_* \
    && sed -i 's|http://archive.ubuntu.com|https://archive.ubuntu.com|g; s|http://security.ubuntu.com|https://security.ubuntu.com|g' /etc/apt/sources.list.d/ubuntu.sources \
    && rm -rf /var/lib/apt/lists/*
COPY --from=node-runtime /usr/local/bin/node /opt/node/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules /opt/node/lib/node_modules
RUN ln -s /opt/node/bin/node /usr/local/bin/node \
    && ln -s /opt/node/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /opt/node/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
COPY versions.env /opt/workstation/versions.env
RUN source /opt/workstation/versions.env \
    && curl -fsSL --retry 4 https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo 'deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] https://dl.google.com/linux/chrome/deb/ stable main' > /etc/apt/sources.list.d/google-chrome.list \
    && curl -fsSL --retry 4 https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-vscode.gpg \
    && echo 'deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-vscode.gpg] https://packages.microsoft.com/repos/code stable main' > /etc/apt/sources.list.d/vscode.list \
    && apt-get update && apt-get install -y --no-install-recommends "google-chrome-stable=$CHROME_VERSION" "code=$VSCODE_VERSION" \
    && rm -rf /var/lib/apt/lists/*
COPY mcp /opt/workstation/mcp
COPY scripts /opt/workstation/scripts
COPY unity /opt/workstation/unity
RUN --mount=type=bind,from=tool-download-cache,target=/mnt/tool-download-cache \
    WORKSTATION_DOWNLOAD_CACHE=/mnt/tool-download-cache bash /opt/workstation/scripts/install-tools.sh
COPY desktop/home-template/ /opt/workstation/home-template/
COPY desktop/bwrap-desktop-compat.c /opt/workstation/desktop/bwrap-desktop-compat.c
RUN install -d /usr/local/libexec/workstation-glycin \
    && gcc -O2 -Wall -Wextra /opt/workstation/desktop/bwrap-desktop-compat.c -o /usr/local/libexec/workstation-glycin/bwrap \
    && chmod -R go-w /opt/workstation/home-template /opt/workstation/desktop /usr/local/libexec/workstation-glycin \
    && chmod 755 /opt/workstation/home-template/Desktop/*.desktop \
    && chmod 644 /opt/workstation/versions.env /opt/workstation/home-template/.claude.json /opt/workstation/home-template/.codex/config.toml \
    && install -o 1100 -g 1100 -m 644 /opt/workstation/home-template/.profile /home/dev/.profile
COPY runtime/ /etc/workstation/
COPY licenses/ /opt/workstation/licenses/
RUN install -m 755 /etc/workstation/entrypoint.py /usr/local/bin/workstation-entrypoint \
    && install -m 755 /opt/workstation/scripts/reset-claude-user.py /usr/local/bin/reset-claude-user \
    && install -m 755 /etc/workstation/start-desktop /usr/local/bin/workstation-desktop \
    && install -m 755 /etc/workstation/start-vnc /usr/local/bin/workstation-vnc \
    && install -m 644 /etc/workstation/sshd_config /etc/ssh/sshd_config \
    && install -m 644 /etc/workstation/supervisord.conf /etc/supervisor/supervisord.conf
EXPOSE 22 5901
HEALTHCHECK --interval=30s --start-period=40s --timeout=5s CMD ["python3", "/etc/workstation/healthcheck.py"]
ENTRYPOINT ["/usr/local/bin/workstation-entrypoint"]
