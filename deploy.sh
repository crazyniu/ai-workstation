#!/bin/sh
set -eu
cd "$(dirname "$0")"
service=
case "${1:-portable}" in
  portable) compose_file=compose.portable.yaml ;;
  gateway-portable) compose_file=compose.portable.yaml; service=gateway ;;
  all) compose_file=compose.yaml ;;
  gateway) compose_file=compose.gateway.yaml ;;
  workstation) compose_file=compose.workstation.yaml ;;
  workstation-bridge) compose_file=workstation/compose.yaml ;;
  *) printf 'Usage: %s [portable|gateway-portable|all|gateway|workstation|workstation-bridge]\n' "$0" >&2; exit 2 ;;
esac
[ "$#" -le 1 ] || { printf 'Expected at most one deployment role.\n' >&2; exit 2; }
# Always use the private root .env, including for the nested bridge example.
compose() { docker compose --env-file .env -f "$compose_file" "$@"; }
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
# Intentional field splitting: service is either empty or the literal gateway.
compose pull $service
compose up -d --wait --wait-timeout 240 $service
printf '\nDeployment ready: %s. Use this same Compose file for later operations.\n' "$compose_file"
