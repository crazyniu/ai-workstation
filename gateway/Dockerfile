ARG BASE_IMAGE=ubuntu:24.04
FROM ${BASE_IMAGE}
ARG TARGETARCH
RUN test "$TARGETARCH" = amd64
ENV DEBIAN_FRONTEND=noninteractive DATA_DIR=/data LANG=C.UTF-8
RUN apt-get update && apt-get install -y --no-install-recommends nginx supervisor python3 python3-yaml ca-certificates iproute2 iptables dnsutils curl procps tini openssh-server git gh && rm -rf /var/lib/apt/lists/* /etc/nginx/sites-enabled/default /etc/ssh/ssh_host_*
COPY app /opt/gateway/app
COPY web /opt/gateway/web
COPY runtime /opt/gateway/runtime
COPY seed/mihomo /opt/gateway/seed/mihomo
COPY seed/adguard /opt/gateway/seed/adguard
COPY seed/tailscale /opt/gateway/seed/tailscale
COPY seed/panel /opt/gateway/seed/panel
COPY seed/filters/adguard-dns.txt seed/filters/manifest.json /opt/gateway/seed/filters/
COPY components.lock.json /opt/gateway/components.lock.json
COPY NOTICE /opt/gateway/NOTICE
COPY licenses /opt/gateway/licenses
COPY runtime/nginx.conf /etc/nginx/nginx.conf
RUN python3 /opt/gateway/runtime/build-info.py \
    && chmod +x /opt/gateway/runtime/start /opt/gateway/runtime/service \
    && chmod -R a+rX /opt/gateway/web /opt/gateway/licenses \
    && mkdir -p /data /run/gateway
EXPOSE 22 80 53/tcp 53/udp 7890/tcp 7890/udp 7891/tcp 7891/udp 41641/udp
LABEL org.opencontainers.image.title="Home Gateway" \
      org.opencontainers.image.description="Mihomo, AdGuard Home, Tailscale and a desktop Web console" \
      org.opencontainers.image.source="https://github.com/crazyniu/ai-workstation"
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD curl --noproxy '*' -fsS http://127.0.0.1/healthz && python3 /opt/gateway/app/healthcheck.py
ENTRYPOINT ["/usr/bin/tini", "--", "/opt/gateway/runtime/start"]
