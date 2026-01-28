FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    MUJOCO_GL=glfw \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

# System deps for mujoco with on-host display + ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    libgl1-mesa-glx libglu1-mesa libglfw3 libglew-dev \
    libx11-6 libxext6 libxrender1 libxrandr2 libxi6 libxcursor1 libxinerama1 libxxf86vm1 \
    ffmpeg git build-essential pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Python deps
RUN python3 -m pip install --upgrade pip \
    && python3 -m pip install uvicorn[standard] fastapi \
    && python3 -m pip install -e .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
