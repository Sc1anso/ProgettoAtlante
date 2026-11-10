#!/usr/bin/env bash
set -Eeuo pipefail

export PATH="${MAMBA_ROOT_PREFIX:-/opt/micromamba}/envs/gsmonitor/bin:$PATH"
# SIBR only needs a display for its remote image window. Force Mesa's software
# GLX implementation for the Xvfb display; CUDA rendering remains in view.py.
export LIBGL_ALWAYS_SOFTWARE=1
export __GLX_VENDOR_LIBRARY_NAME=mesa
export MESA_LOADER_DRIVER_OVERRIDE=llvmpipe

job_root="${JOB_ROOT:-/jobs}"
iteration="${MONITOR_ITERATION:-30000}"
request_file="$job_root/monitor-request.json"
viewer="/monitor/SIBR_viewers/install/bin/SIBR_remoteGaussian_app"
last_request=""
viewer_pid=""
renderer_pid=""

stop_viewer() {
  for pid in "$renderer_pid" "$viewer_pid"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then kill "$pid" 2>/dev/null || true; fi
  done
  renderer_pid=""
  viewer_pid=""
}
trap 'stop_viewer; exit 0' INT TERM

Xvfb :0 -screen 0 1440x900x24 -ac +extension GLX +render -noreset &
sleep 2
x11vnc -display :0 -forever -shared -nopw -rfbport 5900 &
# Recent noVNC packages ship the web client and websockify, but not the old
# novnc_proxy wrapper.  Start websockify explicitly so port 6080 actually
# serves the noVNC client instead of leaving Docker with a published, unused
# port.
websockify --web /usr/share/novnc 6080 localhost:5900 &

echo "Gaussian Monitor ready on noVNC port 6080; waiting for a completed job."
while true; do
  if [[ -f "$request_file" ]]; then
    request="$(cat "$request_file" 2>/dev/null || true)"
    if [[ -n "$request" && "$request" != "$last_request" ]]; then
      job_id="$(printf '%s' "$request" | sed -nE 's/.*"job_id"[[:space:]]*:[[:space:]]*"([a-f0-9-]+)".*/\1/p')"
      scene="$job_root/$job_id/scene"
      model="$job_root/$job_id/output"
      point_cloud="$model/point_cloud/iteration_$iteration/point_cloud.ply"
      if [[ -n "$job_id" && -d "$scene" && -f "$point_cloud" ]]; then
        stop_viewer
        echo "Opening Gaussian Monitor for job $job_id."
        DISPLAY=:0 "$viewer" --ip 127.0.0.1 --port 6009 --rendering-size 1200 800 &
        viewer_pid=$!
        sleep 3
        DISPLAY=:0 micromamba run -n gsmonitor python /monitor/view.py \
          -s "$scene" -m "$model" --iteration "$iteration" --ip 127.0.0.1 --port 6009 &
        renderer_pid=$!
        last_request="$request"
      else
        echo "Ignoring invalid monitor request."
      fi
    fi
  fi
  sleep 2
done
