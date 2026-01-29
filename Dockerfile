FROM ubuntu:22.04

ARG APT_MIRROR=

ENV DEBIAN_FRONTEND=noninteractive \
    MUJOCO_GL=osmesa \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

# Optional mirror swap (fallback to default if not set)
RUN if [ -n "$APT_MIRROR" ]; then \
      sed -i "s@http://archive.ubuntu.com/ubuntu/@${APT_MIRROR}@g" /etc/apt/sources.list && \
      sed -i "s@http://security.ubuntu.com/ubuntu/@${APT_MIRROR}@g" /etc/apt/sources.list ; \
    fi

# System deps for mujoco headless + ffmpeg
RUN apt-get update -o Acquire::Retries=5 -o Acquire::http::Pipeline-Depth=0 \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        python3 python3-pip python3-venv \
        libgl1-mesa-glx libglu1-mesa libglfw3 libglew-dev \
        libosmesa6 libosmesa6-dev \
        libx11-6 libxext6 libxrender1 libxrandr2 libxi6 libxcursor1 libxinerama1 libxxf86vm1 \
        ffmpeg git build-essential pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Python deps
RUN python3 -m pip install --upgrade pip \
    && python3 -m pip install uvicorn[standard] fastapi python-multipart \
    && python3 -m pip install -e .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
