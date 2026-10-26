#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

# Docker and the Tailscale address may not be ready when the user manager starts.
# This script is retried by new-api-compose.service; it changes no host settings.
tailnet_ip=$(sed -n 's/^TAILSCALE_IP=//p' .env)
compose_files=$(sed -n 's/^COMPOSE_FILE=//p' .env)
for ((attempt = 0; attempt < 60; attempt++)); do
  if docker info >/dev/null 2>&1; then
    if [[ "$compose_files" != *docker-compose.tailnet.yml* ]] ||
      ip -4 -o address show | awk '{split($4, address, "/"); print address[1]}' | grep -Fxq -- "$tailnet_ip"; then
      exec docker compose up -d --wait --wait-timeout 180
    fi
  fi
  sleep 2
done
printf '%s\n' 'Docker or the configured Tailscale address is not ready.' >&2
exit 1
