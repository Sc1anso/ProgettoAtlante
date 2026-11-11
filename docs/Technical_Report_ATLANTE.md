# Technical Report — Project ATLANTE

Architecture, requirements, installation, and operations. For workflow and UI details, see the [deployment guide](../server/DEPLOYMENT_AND_USAGE.md) and the [user manual](User_Manual_ATLANTE.md).

## Architecture

- **API/UI:** FastAPI serves the web app, job API/history, viewers, and downloads on TCP port 8084.
- **Queue:** Redis and Celery coordinate isolated jobs in the persistent Docker volume `job-data`.
- **GPU worker:** One worker by default; an optional second worker can be enabled with the `dual-gpu` Compose profile. Each worker processes one job at a time.
- **RGB pipeline:** frame extraction/filtering, mask generation/refinement, GPU COLMAP, RaDe-GS training, `recon.ply` extraction, and viewer preset generation.
- **Prepared COLMAP dataset:** ZIP validation and isolated extraction followed by RaDe-GS and mesh extraction; frame extraction, COLMAP, rembg, and DiGS are skipped.
- **Optional services:** Gaussian Monitor/noVNC on port 50001; Caddy TLS endpoint on port 8443, with port 80 required for ACME validation.

Derived viewer presets, GLB exports, conservative repair results, and video previews do not replace the original PLY. Job data is stored in Docker volumes. Removing containers does not remove volumes; `docker compose down -v` does.

## System requirements

| Resource | Practical starting point | Recommended |
| --- | --- | --- |
| System | x86_64 Linux or WSL2 | Native Linux for a dedicated server |
| GPU | NVIDIA GPU with 16 GB VRAM; compatibility must be verified | Tesla V100 or a GPU validated with the CUDA 12.1 stack; more VRAM for higher presets |
| CPU | 8 cores | 16+ cores for builds and preprocessing |
| RAM | 32 GB | 64 GB for large videos/meshes |
| Free storage | 100 GB SSD | 250 GB+ NVMe, plus capacity for jobs, checkpoints, and Docker cache |
| Software | Docker Compose v2, NVIDIA driver, NVIDIA Container Toolkit | WSL2 with Docker Desktop/WSL integration on Windows |

These are planning guidelines, not guaranteed capacity limits. Video resolution/duration, frame count, preset, and mesh size affect memory, runtime, and storage. The first build compiles CUDA components; the first relevant job may download the rembg model.

### WSL2 notes

Use WSL2 and the NVIDIA driver for WSL installed on Windows. Docker Desktop must be running with integration enabled for the distribution. Do not install a separate Linux NVIDIA driver inside WSL. Keep the repository in the Linux filesystem (not `/mnt/c`) and verify `nvidia-smi` and Docker GPU access before setup.

## Install and start

From the project root:

```bash
bash server/setup-service.sh
```

The setup script supports CentOS/RHEL/Rocky/AlmaLinux 9, Ubuntu, Debian, and WSL2 with Docker Desktop already configured. Where possible, it configures prerequisites, checks container GPU access, builds the image, and starts Redis, the API, and one worker. Open `http://localhost:8084` in WSL or `http://SERVER-IP:8084` on the LAN.

```bash
bash server/start-service.sh  # restart without rebuilding
bash server/stop-service.sh   # stop containers; volumes are preserved
```

### Optional configuration

Enable a second GPU worker only on a host with a second visible NVIDIA GPU. Pass the setting both at setup and when starting later:

```bash
PAVAROTTI_ENABLE_SECOND_GPU=1 bash server/setup-service.sh
PAVAROTTI_ENABLE_SECOND_GPU=1 bash server/start-service.sh
```

The optional Gaussian Monitor is built separately and uses GPU 0:

```bash
PAVAROTTI_ENABLE_MONITOR=1 bash server/setup-service.sh
```

It is exposed on TCP port 50001 and has no project-level authentication. Restrict it to a trusted network. After the main service has been stopped, start an already-built Monitor from `server/` with `docker compose --profile monitor up -d monitor`.

### HTTPS and security

HTTPS is optional and requires a public DNS hostname and public reachability of TCP port 80 for ACME HTTP validation:

```bash
PAVAROTTI_ENABLE_HTTPS=1 PAVAROTTI_PUBLIC_HOST=atlante.example.org bash server/setup-service.sh
```

The HTTPS endpoint uses port 8443. The application has no login, upload quotas, or user management; TLS alone is not sufficient protection for public exposure. Use authentication, upload limits, firewall rules, backups, and a retention policy before any public deployment. Do not commit `server/.env` or real user data. Note: `.env.example` is a template for Compose interpolation; copying it to `.env` does not export variables to the setup/start scripts.

## Repository and distribution

The private GitHub repository is `Sc1anso/ProgettoAtlante`. The demo video is tracked with Git LFS; install Git LFS before cloning if you need the demo endpoint and full checkout. The distributable ZIP contains the project source and the actual demo video but omits Git history, runtime secrets, datasets, generated jobs/results, caches, and compiled artifacts. It is a source package, not a prebuilt image: the first setup downloads dependencies and builds the containers. See [third-party notices](../THIRD_PARTY_NOTICES.md) before redistribution; upstream components have independent license terms and the combined project has no blanket license.
