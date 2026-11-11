#!/usr/bin/env bash
# One-command installer for the Pavarotti 3D service.
# Run from the extracted package root: bash server/setup-service.sh
set -Eeuo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
is_wsl=false
grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null && is_wsl=true
. /etc/os-release

need_sudo() { command -v sudo >/dev/null || { echo 'sudo is required.' >&2; exit 1; }; }
install_rpm_host() {
  need_sudo
  sudo dnf install -y dnf-plugins-core curl
  if ! command -v docker >/dev/null; then
    sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    sudo systemctl enable --now docker
  fi
  if ! command -v nvidia-ctk >/dev/null; then
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo \
      | sudo tee /etc/yum.repos.d/nvidia-container-toolkit.repo >/dev/null
    sudo dnf install -y nvidia-container-toolkit
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker
  fi
}
install_debian_host() {
  # In WSL, Docker Desktop already supplies the daemon and NVIDIA runtime.
  if $is_wsl; then
    command -v docker >/dev/null || { echo 'WSL detected: install/start Docker Desktop with WSL integration first.' >&2; exit 1; }
    docker compose version >/dev/null || { echo 'WSL detected: Docker Compose v2 is required in Docker Desktop.' >&2; exit 1; }
    return
  fi
  need_sudo
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl gnupg
  if ! command -v docker >/dev/null; then
    sudo install -m 0755 -d /etc/apt/keyrings
    docker_distribution="$ID"
    curl -fsSL "https://download.docker.com/linux/${docker_distribution}/gpg" | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/${docker_distribution} $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    sudo systemctl enable --now docker
  fi
  if ! command -v nvidia-ctk >/dev/null; then
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
    sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker
  fi
}

case "$ID" in
  centos|rhel|rocky|almalinux) install_rpm_host ;;
  ubuntu|debian) install_debian_host ;;
  *) echo "Unsupported host: $ID. Install Docker, NVIDIA driver and NVIDIA Container Toolkit manually." >&2; exit 1 ;;
esac

command -v nvidia-smi >/dev/null || { echo 'NVIDIA driver/GPU unavailable on host.' >&2; exit 1; }
if ! docker info >/dev/null 2>&1; then
  need_sudo
  sudo docker info >/dev/null || { echo 'Docker daemon is unavailable.' >&2; exit 1; }
  docker() { sudo docker "$@"; }
  echo 'Using sudo for this setup because the current user cannot access Docker. Use sudo for future Docker commands or ask the system administrator to apply the local Docker access policy.'
fi
docker compose version >/dev/null
docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi >/dev/null

cd "$root/server"
compose_profiles=()
if [[ "${PAVAROTTI_ENABLE_SECOND_GPU:-0}" == "1" ]]; then
  compose_profiles+=(--profile dual-gpu)
fi
if [[ "${PAVAROTTI_ENABLE_HTTPS:-0}" == "1" ]]; then
  [[ -n "${PAVAROTTI_PUBLIC_HOST:-}" ]] || { echo 'PAVAROTTI_PUBLIC_HOST (a public DNS name) is required when HTTPS is enabled.' >&2; exit 1; }
  compose_profiles+=(--profile https)
fi
docker compose build
docker compose "${compose_profiles[@]}" up -d

if [[ "${PAVAROTTI_ENABLE_MONITOR:-0}" == "1" ]]; then
  echo 'Building the optional CUDA 11 Gaussian Monitor (this can take several minutes).'
  docker compose --profile monitor build monitor
  docker compose "${compose_profiles[@]}" --profile monitor up -d monitor
fi

if [[ "${PAVAROTTI_ENABLE_HTTPS:-0}" == "1" ]]; then
  url="https://${PAVAROTTI_PUBLIC_HOST}:8443"
  monitor_host="$PAVAROTTI_PUBLIC_HOST"
elif $is_wsl; then
  url='http://localhost:8084'
  monitor_host=localhost
else
  ip="$(hostname -I | awk '{print $1}')"
  url="http://${ip}:8084"
  monitor_host="$ip"
fi
echo "Project ATLANTE is running: $url"
if [[ "${PAVAROTTI_ENABLE_MONITOR:-0}" == "1" ]]; then
  echo "Gaussian Monitor is running: http://${monitor_host}:50001/vnc.html"
else
  echo 'Optional Gaussian Monitor: PAVAROTTI_ENABLE_MONITOR=1 bash server/setup-service.sh'
fi
if [[ "${PAVAROTTI_ENABLE_SECOND_GPU:-0}" == "1" ]]; then
  echo 'Second GPU worker enabled.'
else
  echo 'One GPU worker enabled. For a second worker: PAVAROTTI_ENABLE_SECOND_GPU=1 bash server/setup-service.sh'
fi
