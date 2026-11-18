#!/bin/sh
set -eu
cd "$(dirname "$0")"
service=
ai_install=false
if [ "${1:-}" = ai ]; then
  ai_install=true
  shift
  case "${1:-all}" in
    all|gateway|workstation) ;;
    *) printf 'Usage: %s ai [all|gateway|workstation]\n' "$0" >&2; exit 2 ;;
  esac
  if [ "$#" -eq 0 ]; then set -- all; fi
fi
case "${1:-portable}" in
  portable) compose_file=compose.portable.yaml ;;
  gateway-portable) compose_file=compose.portable.yaml; service=gateway ;;
  all) compose_file=compose.yaml ;;
  gateway) compose_file=compose.gateway.yaml ;;
  workstation) compose_file=compose.workstation.yaml ;;
  workstation-bridge) compose_file=workstation/compose.yaml ;;
  *) printf 'Usage: %s ai [all|gateway|workstation] or %s [portable|gateway-portable|all|gateway|workstation|workstation-bridge]\n' "$0" "$0" >&2; exit 2 ;;
esac
overlays=
if [ "$#" -gt 1 ]; then
  [ "$#" -eq 2 ] && [ "$2" = --isolate-lan ] || { printf 'Expected a role and optional --isolate-lan.\n' >&2; exit 2; }
  case "$1" in
    gateway) overlays=compose.gateway-isolation.yaml ;;
    workstation) overlays=compose.workstation-isolation.yaml ;;
    all) overlays="compose.gateway-isolation.yaml compose.workstation-isolation.yaml" ;;
    *) printf '%s\n' '--isolate-lan requires a Linux LAN deployment.' >&2; exit 2 ;;
  esac
fi
# Always use the private root .env, including for the nested bridge example.
# These names are fixed above and contain no spaces.
overlay_flags=
for overlay in $overlays; do overlay_flags="$overlay_flags -f $overlay"; done
compose() { docker compose --env-file .env -f "$compose_file" $overlay_flags "$@"; }
if [ ! -f .env ]; then cp .env.example .env; chmod 600 .env; fi
compose config --quiet
if ! existing_containers=$(compose ps --all --quiet); then
  printf 'Unable to check existing containers. Deployment was not started.\n' >&2
  exit 1
fi
if [ -n "$existing_containers" ]; then
  printf '%s\n' 'Existing Compose containers found, including stopped containers.' \
    'deploy.sh only creates a new environment. Use the same Compose file with start or restart for existing containers.' \
    'Before replacing a container, export its internal data and follow the documented restore procedure.' >&2
  exit 1
fi
if [ "$ai_install" = true ]; then
  python3 scripts/ai-install-plan.py "$compose_file" "$1" $overlays
fi
# Intentional field splitting: service is either empty or the literal gateway.
compose pull $service
compose up -d --wait --wait-timeout 240 $service
printf '\nDeployment ready: %s %s. Use the same Compose files for later operations.\n' "$compose_file" "$overlays"
