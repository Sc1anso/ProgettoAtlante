FROM nvidia/cuda:11.6.2-devel-ubuntu20.04

# Docker image builds have no GPU exposed. The server uses Tesla V100 GPUs
# (compute capability 7.0), so CUDA extensions must target that architecture.
ENV DEBIAN_FRONTEND=noninteractive \
    MAMBA_ROOT_PREFIX=/opt/micromamba \
    PATH=/opt/micromamba/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    TORCH_CUDA_ARCH_LIST=7.0

# SIBR needs an X server even when its window is exposed through noVNC. The
# Gaussian rendering itself is performed by view.py on the NVIDIA GPU. Xvfb
# needs the Xorg GLX runtime plus Mesa's software driver for SIBR's GLFW
# window; CUDA remains available to view.py for Gaussian rendering.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates cmake curl git ninja-build \
    libassimp-dev libavcodec-dev libavdevice-dev libavformat-dev libavutil-dev libswscale-dev libboost-all-dev libegl1 \
    libeigen3-dev libembree-dev libgl1-mesa-dev libglew-dev libglfw3-dev \
    libglu1-mesa-dev libgtk-3-dev libx11-xcb1 libxcursor-dev \
    libxi-dev libxinerama-dev libxrandr-dev libxxf86vm-dev \
    libjpeg-dev libpng-dev libtiff-dev libwebp-dev \
    libgl1-mesa-dri mesa-utils novnc websockify x11vnc xvfb xserver-xorg-core \
    && rm -rf /var/lib/apt/lists/*

# Conda's current OpenCV builds target a newer libstdc++ than Ubuntu 20.04.
# Build the version required by SIBR with this image's GCC instead, so that its
# C++ ABI matches the CUDA 11.6 toolchain used for the renderer extensions.
ARG OPENCV_VERSION=4.5.5
RUN curl -fsSL "https://github.com/opencv/opencv/archive/refs/tags/${OPENCV_VERSION}.tar.gz" -o /tmp/opencv.tar.gz \
    && curl -fsSL "https://github.com/opencv/opencv_contrib/archive/refs/tags/${OPENCV_VERSION}.tar.gz" -o /tmp/opencv-contrib.tar.gz \
    && tar -xzf /tmp/opencv.tar.gz -C /tmp \
    && tar -xzf /tmp/opencv-contrib.tar.gz -C /tmp \
    && cmake -S "/tmp/opencv-${OPENCV_VERSION}" -B /tmp/opencv-build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/opt/opencv \
        -DOPENCV_EXTRA_MODULES_PATH="/tmp/opencv_contrib-${OPENCV_VERSION}/modules" \
        -DBUILD_LIST=core,imgproc,imgcodecs,videoio,highgui,calib3d,features2d,ximgproc,optflow \
        -DBUILD_EXAMPLES=OFF -DBUILD_TESTS=OFF -DBUILD_PERF_TESTS=OFF \
        -DBUILD_opencv_python2=OFF -DBUILD_opencv_python3=OFF \
        -DWITH_QT=OFF -DWITH_TBB=OFF \
    && cmake --build /tmp/opencv-build --parallel 4 \
    && cmake --install /tmp/opencv-build \
    && rm -rf /tmp/opencv.tar.gz /tmp/opencv-contrib.tar.gz "/tmp/opencv-${OPENCV_VERSION}" \
        "/tmp/opencv_contrib-${OPENCV_VERSION}" /tmp/opencv-build
RUN curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj -C /usr/local/bin --strip-components=1 bin/micromamba \
    && micromamba create -y -n gsmonitor -c conda-forge python=3.8 pip=22.3.1 'cmake>=3.22,<4' \
    && micromamba clean --all --yes

COPY Gaussian-Splatting-Monitor /monitor
COPY server/monitor/entrypoint.sh /usr/local/bin/monitor-entrypoint
RUN chmod +x /usr/local/bin/monitor-entrypoint \
    && micromamba run -n gsmonitor python -m pip install --no-cache-dir \
      torch==1.12.1+cu116 torchvision==0.13.1+cu116 torchaudio==0.12.1 \
      --extra-index-url https://download.pytorch.org/whl/cu116 \
    && micromamba run -n gsmonitor python -m pip install --no-cache-dir plyfile==0.8.1 tqdm matplotlib \
    && micromamba run -n gsmonitor python -m pip install --no-cache-dir \
      /monitor/submodules/diff-gaussian-rasterization /monitor/submodules/simple-knn \
    && find /monitor/SIBR_viewers/extlibs -type d -name subbuild -prune -exec rm -rf {} + \
    && micromamba run -n gsmonitor cmake -S /monitor/SIBR_viewers -B /monitor/SIBR_viewers/build -DCMAKE_BUILD_TYPE=Release -DOpenCV_DIR=/opt/opencv/lib/cmake/opencv4 \
    && micromamba run -n gsmonitor cmake --build /monitor/SIBR_viewers/build --parallel 4 \
    && micromamba run -n gsmonitor cmake --install /monitor/SIBR_viewers/build

WORKDIR /monitor
EXPOSE 6080
ENTRYPOINT ["/usr/local/bin/monitor-entrypoint"]
