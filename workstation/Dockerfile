ARG NODE_BASE=node:24.22.1-bookworm-slim@sha256:55fb5f5a527ea2c5c4a95f963e48ef90aa38c7b346054fdc8ee9957a2b55d205
ARG WORKSTATION_BASE=debian:trixie-slim@sha256:62bd423aeee912639ca8ee681c2b762cb3e25137e0a92b20be455898a9f034ad
# Optional public artifact cache supplied with --build-context tool-download-cache=PATH.
# Empty by default; downloads always retain the versions.env SHA256 checks.
FROM scratch AS tool-download-cache
FROM ${NODE_BASE} AS node-runtime
FROM ${WORKSTATION_BASE}
ARG DEBIAN_FRONTEND=noninteractive
LABEL org.opencontainers.image.title="AI Workstation" \
      org.opencontainers.image.description="Private, reproducible multi-architecture XFCE development workstation" \
      org.opencontainers.image.source="https://github.com/crazyniu/ai-workstation"
ENV WORKSTATION_COUNTRY=SG WORKSTATION_LANGUAGE=en WORKSTATION_TIMEZONE=Asia/Singapore \
    TZ=Asia/Singapore LANG=en_SG.UTF-8 LC_ALL=en_SG.UTF-8 LANGUAGE=en_SG:en \
    CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS=1 CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS=1
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ARG TARGETARCH
RUN case "$TARGETARCH" in amd64|arm64) ;; *) echo 'Codex and Claude upstream Linux binaries require amd64 or arm64.' >&2; exit 1 ;; esac
COPY versions.env /opt/workstation/versions.env
COPY scripts/install-system.sh /opt/workstation/scripts/install-system.sh
COPY desktop/home-template/ /opt/workstation/home-template/
RUN bash /opt/workstation/scripts/install-system.sh
COPY --from=node-runtime /usr/local/bin/node /opt/node/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules /opt/node/lib/node_modules
RUN ln -s /opt/node/bin/node /usr/local/bin/node \
    && ln -s /opt/node/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /opt/node/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
COPY mcp /opt/workstation/mcp
COPY scripts /opt/workstation/scripts
COPY unity /opt/workstation/unity
RUN --mount=type=bind,from=tool-download-cache,target=/mnt/tool-download-cache \
    WORKSTATION_DOWNLOAD_CACHE=/mnt/tool-download-cache bash /opt/workstation/scripts/install-tools.sh
COPY desktop/bwrap-desktop-compat.c /opt/workstation/desktop/bwrap-desktop-compat.c
COPY web-desktop/ /opt/workstation/web-desktop/
COPY runtime/ /etc/workstation/
COPY licenses/ /opt/workstation/licenses/
RUN bash /opt/workstation/scripts/install-runtime.sh
EXPOSE 22 5901 6080
HEALTHCHECK --interval=30s --start-period=40s --timeout=5s CMD ["python3", "/etc/workstation/healthcheck.py"]
ENTRYPOINT ["/usr/local/bin/workstation-entrypoint"]
