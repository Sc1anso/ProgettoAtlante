#!/usr/bin/env bash
# Creates a transferable source archive without runtime data or host build products.
set -Eeuo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
archive="${1:-$root/../ProgettoAtlante.tar.gz}"
cd "$root"
mkdir -p "$(dirname "$archive")"
tar -czf "$archive" --transform='s,^,ProgettoAtlante/,' \
  --exclude-vcs \
  --exclude='**/.env' --exclude='**/.env.local' --exclude='**/.env.*.local' \
  --exclude='data' --exclude='outputs' --exclude='reconstructed_runs' --exclude='jobs' \
  --exclude='RaDe-GS/output' --exclude='RaDe-GS/SIBR_viewers' \
  --exclude='SuGaR/gaussian_splatting/SIBR_viewers' --exclude='SuGaR/output' --exclude='SuGaR/output_models' \
  --exclude='**/__pycache__' --exclude='**/*.pyc' --exclude='**/*.pyo' \
  --exclude='**/node_modules' --exclude='**/build' --exclude='**/.pytest_cache' \
  --exclude='**/CMakeCache.txt' --exclude='**/CMakeFiles' --exclude='**/_deps' \
  --exclude='**/subbuild' --exclude='**/cmake_install.cmake' \
  --exclude='**/*.o' --exclude='**/*.so' --exclude='**/*.a' \
  README.md .gitattributes .gitignore .dockerignore THIRD_PARTY_NOTICES.md \
  RaDe-GS SuGaR DiGS Gaussian-Splatting-Monitor zed-capture-client server docs
printf 'Created %s\n' "$archive"
