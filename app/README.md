# GMR Render Service (FastAPI)

This service takes a GVHMR `.pt` file, retargets it to a chosen robot, and returns an MP4.

## Run locally (conda env)
```bash
conda activate GMR
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Run via Docker
```bash
docker compose up --build
```
Volumes:
- `./assets/body_models` → `/app/assets/body_models` (SMPL-X models, read-only)
- `./videos` → `/app/videos` (outputs)

This service renders headlessly using MuJoCo’s offscreen renderer (`MUJOCO_GL=osmesa`). No display/X forwarding is needed. GPU: if you prefer EGL, set `MUJOCO_GL=egl` and uncomment the NVIDIA block in `docker-compose.yml`.

### APT mirror (Docker)
The Dockerfile accepts `--build-arg APT_MIRROR=...` if you need a local mirror. Leave it empty to use Ubuntu defaults:
```
docker compose build --no-cache --build-arg APT_MIRROR=
```
or set e.g.
```
docker compose build --no-cache --build-arg APT_MIRROR=http://mirrors.tuna.tsinghua.edu.cn/ubuntu/
```

## API
- `GET /healthz` — liveness check
- `POST /render` — form-data:
  - `file` (required): GVHMR `.pt`
  - `robot` (optional, default `unitree_g1`)
  - `width` (optional): video width
  - `height` (optional): video height
Returns MP4 file.

Dependency note: form uploads require `python-multipart` (now included in the Dockerfile and `setup.py`).

## Resolution & Camera
- Default render size: `DEFAULT_WIDTH`/`DEFAULT_HEIGHT` in `app/main.py` (currently 540x960). Override per request with `width`/`height`.
- Camera (headless renderer) is set in `app/main.py`:
  - Tracks robot base (`ROBOT_BASE_DICT[robot]`)
  - `distance` from `VIEWER_CAM_DISTANCE_DICT[robot]`
  - `elevation = -10`
  - `azimuth = 270` (front-facing)
Adjust those constants in `app/main.py` if you want a different view.

## CLI test
```bash
python test_render.py --pt hmr4d_results.pt --out out.mp4
```
Use `--server` to point at a remote instance and `--robot` to change the target robot.
