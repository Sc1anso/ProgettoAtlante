# Contributing to Project ATLANTE

Before proposing a change, read the [project README](README.md), the [deployment guide](server/DEPLOYMENT_AND_USAGE.md), and [third-party license notes](THIRD_PARTY_NOTICES.md). This repository combines components with independent licenses; preserve upstream notices and do not add a project-wide license without a rights review.

## Change guidelines

- Do not commit historical datasets, user videos, reconstruction outputs, checkpoints, credentials, or `server/.env`.
- Keep CUDA/CMake build products, caches, Docker volumes, and generated outputs out of version control. Check redistribution rights before adding large binary assets; use Git LFS only when needed.
- Keep the RGB and prepared-COLMAP flows aligned with the documentation. Document changes to modes, parameters, ports, or persistence.
- Do not expose the API or noVNC without authentication. Never add private IP addresses, tokens, or internal hostnames to documentation.

## Local checks

For container changes, check shell syntax (`bash -n ...`) and Compose configuration (`cd server && docker compose config --quiet`). Run the relevant unit tests when their dependencies are available. A real training run is not a routine test: it requires a GPU, significant time, and storage.

CUDA builds can be lengthy and memory-intensive. Report which checks you ran and which you did not run.
