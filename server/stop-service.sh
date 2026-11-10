#!/usr/bin/env bash
# Stop Pavarotti 3D containers while preserving Docker volumes (jobs and results).
# Run from anywhere: bash server/stop-service.sh
set -Eeuo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root/server"

command -v docker >/dev/null || { echo 'Docker is not installed or not in PATH.' >&2; exit 1; }
docker compose --profile monitor down
echo 'Pavarotti 3D has stopped. Job data remains in the Docker volume.'
