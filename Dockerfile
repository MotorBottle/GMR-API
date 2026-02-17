FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    MUJOCO_GL=egl \
    PYOPENGL_PLATFORM=egl \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

# System deps for MuJoCo headless/EGL + Python + ffmpeg
RUN apt-get update -o Acquire::Retries=5 -o Acquire::http::Pipeline-Depth=0 \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        python3 python3-pip python3-venv \
        libgl1-mesa-glx libglu1-mesa libglfw3 libglew-dev \
        libegl1 libgles2 libglvnd0 \
        libosmesa6 libosmesa6-dev \
        libx11-6 libxext6 libxrender1 libxrandr2 libxi6 libxcursor1 libxinerama1 libxxf86vm1 \
        ffmpeg git build-essential pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN python3 -m pip install --upgrade pip \
    && python3 -m pip install uvicorn[standard] fastapi python-multipart \
    && python3 -m pip install -e .

EXPOSE 8000
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
