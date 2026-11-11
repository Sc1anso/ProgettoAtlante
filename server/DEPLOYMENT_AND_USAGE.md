# Deployment, usage, and operations

This guide covers native Linux and WSL2 installation, the current user-facing modes, optional service profiles, and troubleshooting. See the [project README](../README.md) for an overview.

## 1. Requirements

- x86_64 Linux (CentOS/RHEL/Rocky/AlmaLinux 9, Ubuntu, or Debian) or WSL2.
- NVIDIA GPU and a host driver compatible with the CUDA 12.1 container; NVIDIA Container Toolkit is required for Docker GPU access. The build target is Tesla V100 / compute capability 7.0.
- Practical starting point: 8 CPU cores, 32 GB RAM, 16 GB VRAM, and 100 GB of free SSD space. For larger jobs, 16+ cores, 64 GB RAM, more VRAM, and 250 GB+ NVMe are recommended.
- Docker Engine with Compose v2. On WSL2, Docker Desktop must be running with WSL integration and GPU access enabled. Keep the checkout in the Linux filesystem rather than `/mnt/c`.
- Internet access for the first image build and dependency downloads; rembg may download its model during the first relevant job.

These are planning figures, not hard guarantees. Video resolution/duration, preset, frame count, and mesh size affect memory, runtime, and disk usage.

## 2. Install and start

From the repository root:

```bash
bash server/setup-service.sh
```

The script installs prerequisites where supported, checks GPU access from Docker, builds the application image, and starts Redis, the API/web UI, and one GPU worker. Open `http://localhost:8084` from Windows/WSL2, or `http://SERVER-IP:8084` from the LAN.

For a two-GPU host, enable the second worker during setup:

```bash
PAVAROTTI_ENABLE_SECOND_GPU=1 bash server/setup-service.sh
```

For everyday use:

```bash
bash server/start-service.sh
bash server/stop-service.sh
```

Start reuses existing images. Stop preserves named volumes. Avoid `docker compose down -v` unless you intend to delete stored jobs and results.

### WSL2

Use WSL2, install the NVIDIA Windows driver with WSL support, and enable the distribution in Docker Desktop's WSL Integration settings. Do not install a separate Linux NVIDIA driver inside the WSL distribution. Before setup, verify `nvidia-smi`, `docker compose version`, and GPU access with:

```bash
docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi
```

Keep the source tree inside the WSL Linux filesystem for better build and file-I/O performance.

## 3. Optional profiles and configuration

### Second GPU worker

`PAVAROTTI_ENABLE_SECOND_GPU=1` enables Compose profile `dual-gpu`, which adds `worker-v100-1`. It requires a second visible NVIDIA GPU. Set the variable both for setup and for later starts:

```bash
PAVAROTTI_ENABLE_SECOND_GPU=1 bash server/setup-service.sh
PAVAROTTI_ENABLE_SECOND_GPU=1 bash server/start-service.sh
```

Each worker processes one GPU job at a time. A job submitted while its worker is busy remains queued.

### Gaussian Splatting Monitor

The optional Monitor is built separately, uses GPU 0, and serves noVNC on TCP port `50001`:

```bash
PAVAROTTI_ENABLE_MONITOR=1 bash server/setup-service.sh
```

Or, after the main setup, from `server/`:

```bash
docker compose --profile monitor build monitor
docker compose --profile monitor up -d monitor
```

After `server/stop-service.sh` stops all profiles, restart the Monitor with `docker compose --profile monitor up -d monitor`. It reads job data read-only but can compete with worker 0 for VRAM. noVNC has no project login layer; restrict port 50001 to a trusted network.

### HTTPS through Caddy

The optional HTTPS profile requires a public DNS hostname pointing to the server. Forward/reach TCP port 80 from the public Internet for ACME HTTP validation, and TCP port 8443 to the service for browser access. The included Caddy configuration does not use DNS challenges; HTTPS certificate issuance fails if port 80 cannot be reached.

```bash
PAVAROTTI_ENABLE_HTTPS=1 PAVAROTTI_PUBLIC_HOST=atlante.example.org bash server/setup-service.sh
```

Open `https://atlante.example.org:8443`. Pass both variables again when restarting:

```bash
PAVAROTTI_ENABLE_HTTPS=1 PAVAROTTI_PUBLIC_HOST=atlante.example.org bash server/start-service.sh
```

`server/.env.example` is a template for Compose interpolation; copying it to `.env` alone does not export variables to the setup/start scripts. HTTPS provides TLS only: this application has no user authentication, upload quotas, or account controls. Do not expose it directly to the public Internet; put an authenticated reverse proxy and appropriate upload/storage policies in front of it.

## 4. Input modes

The current visible UI offers **RGB video** and **Prepared COLMAP dataset**. ZED/DiGS backend routes remain in the source for compatibility, but the ZED selector and direct-capture panel are hidden in the current UI.

### RGB video

Upload an MP4, MOV, MKV, or WebM file. The server extracts frames according to the selected quality profile, filters blurry frames, creates/refines masks, runs GPU COLMAP and RaDe-GS, extracts the mesh, and prepares web-viewer assets.

Current RGB preset parameters:

| UI label | Frame sampling | Training iterations | Notes |
| --- | ---: | ---: | --- |
| Fast (`Rapida`) | 1 FPS | 15,000 | Quick check, lower detail |
| Balanced (`Bilanciata`) | 1.5 FPS | 22,000 | Recommended starting point |
| High (`Alta`) | 2 FPS | 30,000 | More detail and runtime |
| Very High (`Molto alta`) | 4 FPS | 45,000 | Highest current preset; needs clean input and more resources |

These settings are implementation defaults and may change between releases. Presets also affect additional pipeline parameters.

### Prepared COLMAP dataset

Upload a ZIP archive. It may contain the dataset folders directly or a single outer scene directory. Minimum structure:

```text
dataset.zip
└── scene-name/                 # optional single outer folder
    ├── images/
    │   └── 0001.jpg
    └── sparse/0/
        ├── cameras.bin
        ├── images.bin
        └── points3D.bin
```

`images/` must contain at least one PNG/JPG/JPEG. `input/` and optional folders such as `masks/`, `input_masks/`, `distorted/`, or `stereo/` are retained if present. Unsafe paths, absolute paths, symlinks, duplicate paths, incomplete structures, and archives exceeding safety limits are rejected. DiGS scenes with the `_densified` suffix are useful candidates; this direct mode does not run DiGS densification again.

### ZED/DiGS compatibility

The source retains the legacy ZED/DiGS worker route and capture client. The ZED ZIP format has `recording.mp4`, `depth_data.dp`, and `camera_data.dp` at the ZIP root, but the corresponding selector is currently hidden in the web UI. Do not treat it as an enabled user-facing mode without deliberately changing the UI.

## 5. Presets, results, and persistence

Each worker processes one job at a time; additional jobs wait for a worker. Completed jobs retain the original `output/recon.ply`. Browser viewer meshes, GLB downloads, Gaussian previews, and conservative repair results are derived assets and do not overwrite the original PLY.

Docker named volumes: `job-data` stores job inputs/results/logs; `rembg-models` caches segmentation models. Back up important volumes and plan disk retention. `docker compose down` preserves them; `docker compose down -v` deletes them.

## 6. Operations and logs

From `server/`:

```bash
docker compose ps
docker compose logs -f api
docker compose logs -f worker-v100-0
docker compose restart
docker compose up -d
```

For the optional Monitor:

```bash
docker compose --profile monitor logs -f monitor
docker compose --profile monitor up -d monitor
docker compose --profile monitor stop monitor
```

To rebuild after source changes, use `docker compose build` followed by `docker compose up -d`. Recreating a worker interrupts its active task; check for running jobs first.

## 7. Troubleshooting

| Symptom | Check |
| --- | --- |
| UI is unreachable | Check `docker compose ps`, host firewall, and TCP 8084. |
| Container cannot see the GPU | Check host `nvidia-smi`, NVIDIA Container Toolkit, or WSL integration; run the GPU test above. |
| Job is waiting for GPU | A worker handles one job at a time; check active jobs and worker logs. |
| Job failed | Inspect `docker compose logs -f worker-v100-0` and the job's `worker.log` in `job-data`. |
| COLMAP reconstruction fails | Use sharp, overlapping views with parallax and texture; keep the subject still and avoid glare. |
| Room/background appears in the mesh | Improve subject/background separation and mask quality in the input video; hole repair does not remove background geometry. |
| HTTPS certificate is not issued | Confirm public DNS and external TCP 80 reachability for ACME; TCP 8443 is used for browser access. |
| Monitor cannot be reached | Confirm Monitor profile/container is running, TCP 50001 is reachable, and the host has enough GPU memory. |

## 8. References

- [User manual](../docs/User_Manual_ATLANTE.md)
- [Technical report](../docs/Technical_Report_ATLANTE.md)
- [Third-party license notes](../THIRD_PARTY_NOTICES.md)
