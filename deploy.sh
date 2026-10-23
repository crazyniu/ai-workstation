#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -f .env ]; then cp .env.example .env; chmod 600 .env; fi
docker compose config --quiet
if ! existing_containers=$(docker compose ps --all --quiet); then
  printf 'Unable to check existing containers. Deployment was not started.\n' >&2
  exit 1
fi
if [ -n "$existing_containers" ]; then
  printf '%s\n' 'Existing Compose containers found, including stopped containers.' \
    'deploy.sh only creates a new environment. Use docker compose start or restart for existing containers.' \
    'Before replacing a container, export its internal data and follow the documented restore procedure.' >&2
  exit 1
fi
docker compose pull
docker compose up -d --wait --wait-timeout 240
printf '\nDeployment ready. Read the configured gateway address in .env.\n'
