# Project ATLANTE

![Platform: Linux and WSL2](https://img.shields.io/badge/platform-Linux%20%7C%20WSL2-4C566A?logo=linux&logoColor=white)
![Docker Compose v2](https://img.shields.io/badge/Docker%20Compose-v2-2496ED?logo=docker&logoColor=white)
![CUDA 12.1](https://img.shields.io/badge/CUDA-12.1-76B900?logo=nvidia&logoColor=white)
![Python 3.9](https://img.shields.io/badge/Python-3.9-3776AB?logo=python&logoColor=white)
![Git LFS](https://img.shields.io/badge/Git%20LFS-enabled-f64935)

Project ATLANTE is a self-hosted web application for reconstructing and inspecting 3D meshes from RGB video or an already prepared COLMAP dataset. It orchestrates frame preparation, masking, COLMAP, RaDe-GS training, mesh extraction, and browser-based viewers using Docker Compose.

> **Licensing:** This repository integrates upstream research software with independent license terms, including research/non-commercial restrictions. No blanket license is granted for the combined project. Review [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the original notices before redistribution or use. Keeping this repository private does not replace license compliance.

## Features

- Reconstruct a scene from an RGB video or a prepared COLMAP ZIP archive.
- Choose among Fast, Balanced, High, and Very High reconstruction presets.
- Track multiple jobs, browse reconstruction history, and view mesh/Gaussian previews.
- Download the original PLY or a quality-selected GLB; optionally attempt conservative small-boundary repair.
- Upload a video from a phone using a QR code.
- Optionally enable the Gaussian Splatting Monitor in a separate container.

The RGB pipeline extracts and filters frames, refines masks, runs COLMAP and RaDe-GS, and writes `output/recon.ply`. The prepared-COLMAP pipeline validates and extracts the dataset, then runs RaDe-GS and mesh extraction without repeating frame extraction, COLMAP, rembg, or DiGS. Jobs and results are stored in the persistent Docker volume `job-data`; rembg models use `rembg-models`.

## Requirements

- x86_64 Linux or WSL2; Docker Engine with Compose v2 (or Docker Desktop with WSL integration).
- NVIDIA GPU, compatible host driver, and NVIDIA Container Toolkit. The build targets CUDA 12.1 and is validated against Tesla V100 (compute capability 7.0).
- Recommended starting point: 8 CPU cores, 32 GB RAM, 16 GB VRAM, and 100 GB free SSD space. Long videos and high presets need more resources.
- Internet access for the first image build and dependency/model downloads. In WSL2, keep the checkout in the Linux filesystem rather than under `/mnt/c`.

These are planning guidelines, not guaranteed capacity limits. Workload size and GPU compatibility vary.

## Quick start

From the repository root:

```bash
bash server/setup-service.sh
```

Open `http://localhost:8084` from Windows/WSL2, or `http://SERVER-IP:8084` from the LAN. To restart existing containers without rebuilding, use `bash server/start-service.sh`; to stop them while keeping Docker volumes, use `bash server/stop-service.sh`.

## Optional profiles

**Second GPU worker** (requires a second NVIDIA GPU):

```bash
PAVAROTTI_ENABLE_SECOND_GPU=1 bash server/setup-service.sh
PAVAROTTI_ENABLE_SECOND_GPU=1 bash server/start-service.sh
```

**Gaussian Monitor** (separate build, uses GPU 0):

```bash
PAVAROTTI_ENABLE_MONITOR=1 bash server/setup-service.sh
```

After `server/stop-service.sh`, start the already-built Monitor separately from `server/` with `docker compose --profile monitor up -d monitor`. The Monitor is exposed on port `50001` and has no added authentication; keep it on a trusted network.

**HTTPS via Caddy** requires a public DNS hostname and an externally reachable TCP port 80 for ACME validation. The HTTPS endpoint is published on port `8443`; there is no built-in login/authentication. Do not expose the app or noVNC directly to the public Internet.

```bash
PAVAROTTI_ENABLE_HTTPS=1 PAVAROTTI_PUBLIC_HOST=atlante.example.org bash server/setup-service.sh
# The same options are needed when restarting the HTTPS profile:
PAVAROTTI_ENABLE_HTTPS=1 PAVAROTTI_PUBLIC_HOST=atlante.example.org bash server/start-service.sh
```

Then open `https://atlante.example.org:8443`. The deployment guide explains the port forwarding and security limitations.

## Documentation

- [Deployment, usage, and troubleshooting](server/DEPLOYMENT_AND_USAGE.md)
- [Server operations](server/README.md)
- [User manual — Markdown](docs/User_Manual_ATLANTE.md) · [formatted DOCX](docs/User_Manual_ATLANTE.docx)
- [Technical report — Markdown](docs/Technical_Report_ATLANTE.md) · [formatted DOCX](docs/Technical_Report_ATLANTE.docx)
- [Third-party software and license notes](THIRD_PARTY_NOTICES.md)
- [Contributing guide](CONTRIBUTING.md)

## Git LFS and repository contents

The demo video at `server/samples/pavarotti-demo.mp4` is tracked with Git LFS because it is larger than GitHub's regular per-file limit. Install Git LFS before cloning if you need the demo endpoint and a complete checkout. Runtime `.env` files, datasets, jobs, generated outputs, caches, and compiled artifacts are excluded.
