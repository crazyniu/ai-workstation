#!/bin/bash
set -euo pipefail
set -a
source /etc/ai-workstation-native.env
set +a
export DATA_DIR=/var/lib/ai-gateway GATEWAY_INSTALL_MODE=native GATEWAY_MODE=false
export GATEWAY_TAILSCALE_TUN=userspace-networking GATEWAY_WEB_PORT=8080 GATEWAY_SSH_PORT=2223
export GATEWAY_BIND_ADDRESS=127.0.0.1 WORKSTATION_BIND_ADDRESS=127.0.0.1 NOVNC_BIND=127.0.0.1
export GATEWAY_CORE_DNS_LISTEN=127.0.0.1:1053 GATEWAY_CORE_DNS_UPSTREAM=127.0.0.1:1053
bash /opt/gateway/runtime/start &
gateway_pid=$!
export WORKSTATION_INSTALL_MODE=native WORKSTATION_SSH_PORT=2222
/usr/local/bin/workstation-entrypoint &
workstation_pid=$!
trap 'kill "$gateway_pid" "$workstation_pid" 2>/dev/null || true; wait || true' EXIT
wait -n "$gateway_pid" "$workstation_pid"
