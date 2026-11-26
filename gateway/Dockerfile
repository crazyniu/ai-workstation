ARG BASE_IMAGE=debian:trixie-slim@sha256:62bd423aeee912639ca8ee681c2b762cb3e25137e0a92b20be455898a9f034ad
# ttyd, the Web terminal, built from its pinned upstream source for every image CPU.
# Debian trixie does not package it, and upstream publishes no riscv64 or ARMv5 build.
FROM ${BASE_IMAGE} AS terminal
ARG TTYD_VERSION=1.7.7
ARG TTYD_SHA256=039dd995229377caee919898b7bd54484accec3bba49c118e2d5cd6ec51e3650
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl build-essential cmake libjson-c-dev libwebsockets-dev libuv1-dev zlib1g-dev libssl-dev \
    && curl -fsSL --retry 3 -o /tmp/ttyd.tar.gz "https://github.com/tsl0922/ttyd/archive/refs/tags/${TTYD_VERSION}.tar.gz" \
    && echo "${TTYD_SHA256}  /tmp/ttyd.tar.gz" | sha256sum -c - \
    && mkdir /src && tar -xzf /tmp/ttyd.tar.gz -C /src --strip-components=1 \
    && cmake -S /src -B /build -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /build -j"$(nproc)" \
    && install -D -m 0755 /build/ttyd /out/ttyd

FROM ${BASE_IMAGE}
ARG TARGETARCH
ARG TARGETVARIANT
ENV DEBIAN_FRONTEND=noninteractive DATA_DIR=/data LANG=C.UTF-8
RUN apt-get update && apt-get install -y --no-install-recommends locales tzdata nginx supervisor python3 python3-yaml ca-certificates iproute2 iptables nftables dnsutils curl procps tini openssh-server git gh libwebsockets19t64 libwebsockets-evlib-uv libjson-c5 libuv1t64 \
    && sed -i '/^root:/s|:/root:|:/data/home:|' /etc/passwd \
    && rm -rf /var/lib/apt/lists/* /etc/nginx/sites-enabled/default /etc/ssh/ssh_host_*
COPY app /opt/gateway/app
COPY web /opt/gateway/web
COPY runtime /opt/gateway/runtime
COPY seed/mihomo /opt/gateway/seed/mihomo
COPY seed/adguard /opt/gateway/seed/adguard
COPY seed/tailscale /opt/gateway/seed/tailscale
COPY seed/panel /opt/gateway/seed/panel
COPY seed/filters/adguard-dns.txt seed/filters/manifest.json /opt/gateway/seed/filters/
COPY seed/architecture /opt/gateway/seed/architecture
COPY components.lock.json /opt/gateway/components.lock.json
COPY NOTICE /opt/gateway/NOTICE
COPY licenses /opt/gateway/licenses
COPY runtime/nginx.conf /etc/nginx/nginx.conf
COPY --from=terminal /out/ttyd /usr/local/bin/ttyd
RUN arch="$TARGETARCH"; if [ "$arch" = arm ]; then arch="arm$TARGETVARIANT"; fi; test "$(cat /opt/gateway/seed/architecture)" = "$arch" \
    && /usr/local/bin/ttyd --version \
    && python3 /opt/gateway/runtime/build-info.py \
    && chmod +x /opt/gateway/runtime/start /opt/gateway/runtime/service \
    && chmod -R a+rX /opt/gateway/web /opt/gateway/licenses \
    && mkdir -p /data /run/gateway
EXPOSE 22 80 53/tcp 53/udp 7890/tcp 7890/udp 7891/tcp 7891/udp 41641/udp
LABEL org.opencontainers.image.title="Home Gateway" \
      org.opencontainers.image.description="Mihomo, AdGuard Home, Tailscale and a desktop Web console" \
      org.opencontainers.image.source="https://github.com/crazyniu/ai-workstation"
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD curl --noproxy '*' -fsS http://127.0.0.1/healthz && python3 /opt/gateway/app/healthcheck.py
ENTRYPOINT ["/usr/bin/tini", "--", "/opt/gateway/runtime/start"]
