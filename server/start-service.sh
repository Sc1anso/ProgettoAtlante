#!/usr/bin/env bash
# Start the already-built Pavarotti 3D service without rebuilding images.
# Run from anywhere: bash server/start-service.sh
set -Eeuo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root/server"

command -v docker >/dev/null || { echo 'Docker is not installed or not in PATH.' >&2; exit 1; }
docker info >/dev/null
docker compose version >/dev/null
compose_profiles=()
if [[ "${PAVAROTTI_ENABLE_SECOND_GPU:-0}" == "1" ]]; then
  compose_profiles+=(--profile dual-gpu)
fi
if [[ "${PAVAROTTI_ENABLE_HTTPS:-0}" == "1" ]]; then
  [[ -n "${PAVAROTTI_PUBLIC_HOST:-}" ]] || { echo 'PAVAROTTI_PUBLIC_HOST is required when HTTPS is enabled.' >&2; exit 1; }
  compose_profiles+=(--profile https)
fi
docker compose "${compose_profiles[@]}" up -d --no-build

if [[ "${PAVAROTTI_ENABLE_HTTPS:-0}" == "1" ]]; then
  url="https://${PAVAROTTI_PUBLIC_HOST}"
elif grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; then
  url='http://localhost:8084'
else
  ip="$(hostname -I | awk '{print $1}')"
  url="http://${ip}:8084"
fi
echo "Pavarotti 3D is running: $url"
