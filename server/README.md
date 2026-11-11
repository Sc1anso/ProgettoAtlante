# Server operations

For supported platforms, installation, user workflows, configuration options, and troubleshooting, see [DEPLOYMENT_AND_USAGE.md](DEPLOYMENT_AND_USAGE.md). For an overview of the whole project, see the [root README](../README.md).

## Setup and daily use

Run these commands from the repository root:

```bash
bash server/setup-service.sh
bash server/start-service.sh
bash server/stop-service.sh
```

Setup builds the images and starts Redis, the API/web UI, and one GPU worker. Start reuses existing images without rebuilding. Stop preserves Docker volumes (jobs, meshes, and caches); do not run `docker compose down -v` if you need the stored results.

Optional setup flags:

```bash
PAVAROTTI_ENABLE_SECOND_GPU=1 bash server/setup-service.sh
PAVAROTTI_ENABLE_MONITOR=1 bash server/setup-service.sh
PAVAROTTI_ENABLE_HTTPS=1 PAVAROTTI_PUBLIC_HOST=atlante.example.org bash server/setup-service.sh
```

Re-pass the relevant `PAVAROTTI_*` variables when using `start-service.sh`; the scripts do not persist shell options. HTTPS uses Caddy, a public DNS hostname, externally reachable TCP 80 for ACME validation, and TCP 8443 for the HTTPS UI. No application authentication is configured, so do not expose the services directly to the Internet.

## Compose and logs

From the `server/` directory:

```bash
docker compose ps
docker compose logs -f api
docker compose logs -f worker-v100-0
docker compose --profile monitor logs -f monitor
```

After `stop-service.sh`, restart the optional Monitor with `docker compose --profile monitor up -d monitor` from `server/`. It must have been built at least once. Persistent data lives in the `job-data` and `rembg-models` volumes. See the deployment guide for backups, retention, ZIP formats, and operational limits.
