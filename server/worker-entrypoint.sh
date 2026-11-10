#!/usr/bin/env bash
set -euo pipefail

# COLMAP's CUDA SIFT implementation needs a GLX context. Each headless worker
# gets its own private X server, while NVIDIA Container Toolkit supplies the
# actual driver libraries and GPU device.
export DISPLAY="${DISPLAY:-:99}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
Xvfb "$DISPLAY" -screen 0 1280x1024x24 -nolisten tcp -noreset &
xvfb_pid=$!
trap 'kill "$xvfb_pid" 2>/dev/null || true' EXIT

for _ in $(seq 1 50); do
    [ -S "/tmp/.X11-unix/X${DISPLAY#:}" ] && break
    sleep 0.1
done

exec micromamba run -n radegs celery -A app.worker.celery_app worker --loglevel=INFO --concurrency=1
