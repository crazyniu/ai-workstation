#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -f .env ]; then cp .env.example .env; chmod 600 .env; fi
docker compose config --quiet
docker compose pull
docker compose up -d --wait --wait-timeout 240
printf '\nDeployment ready. Read the configured gateway address in .env.\n'
