FROM nvidia/cuda:12.1.1-devel-ubuntu22.04

# Docker image builds have no GPU exposed. The deployment target is Tesla V100
# (compute capability 7.0), so make the CUDA extension target explicit.
ENV DEBIAN_FRONTEND=noninteractive \
    MAMBA_ROOT_PREFIX=/opt/micromamba \
    PATH=/opt/micromamba/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    QT_QPA_PLATFORM=offscreen \
    TORCH_CUDA_ARCH_LIST=7.0

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates cmake curl ffmpeg git colmap libegl1 libgl1 libopengl0 libglib2.0-0 ninja-build xvfb \
    && rm -rf /var/lib/apt/lists/*
RUN curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj -C /usr/local/bin --strip-components=1 bin/micromamba \
    && micromamba create -y -n radegs -c conda-forge python=3.9 cmake cgal gmp \
    && micromamba clean --all --yes

COPY RaDe-GS /app/RaDe-GS
COPY SuGaR /app/SuGaR
COPY DiGS /app/DiGS
WORKDIR /app/RaDe-GS

# CUDA 12.1 matches the PyTorch wheels and is supported by Tesla V100 (compute 7.0).
# The source package can contain CMake metadata created on another host.
RUN micromamba run -n radegs python -m pip install --no-cache-dir \
      torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121 \
    && micromamba run -n radegs python -m pip install --no-cache-dir -r requirements.txt \
      pymeshlab fastapi 'uvicorn[standard]' celery redis python-multipart \
      open3d opencv-python scipy scikit-learn matplotlib pandas tqdm 'rembg[gpu]' 'qrcode[pil]' \
    && micromamba run -n radegs python -m pip install --no-cache-dir submodules/diff-gaussian-rasterization submodules/simple-knn \
    && micromamba run -n radegs bash -lc 'cd submodules/tetra_triangulation && rm -rf CMakeCache.txt CMakeFiles _deps && cmake -DCMAKE_POLICY_VERSION_MINIMUM=3.5 . && cmake --build . -j$(nproc) && python -m pip install -e .'

# Keep the expensive dependency layer independent from API/UI changes.
COPY server/app /app/server/app
COPY server/samples /app/server/samples
COPY server/worker-entrypoint.sh /usr/local/bin/worker-entrypoint
RUN chmod +x /usr/local/bin/worker-entrypoint

WORKDIR /app/server
