# GMR Render Service (FastAPI)

This service takes motion input (GVHMR `.pt` or SMPL-X `.npz`), retargets to a robot, and returns selected outputs.

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
- `./assets/body_models` -> `/app/assets/body_models` (SMPL-X models, read-only)
- `./videos` -> `/app/videos` (outputs)

This service renders headlessly using MuJoCo offscreen renderer (`MUJOCO_GL=osmesa`). No display/X forwarding is needed. If you prefer EGL, set `MUJOCO_GL=egl` and uncomment the NVIDIA block in `docker-compose.yml`.

### APT mirror (Docker)
The Dockerfile accepts `--build-arg APT_MIRROR=...` if you need a local mirror. Leave it empty to use Ubuntu defaults:
```bash
docker compose build --no-cache --build-arg APT_MIRROR=
```
or set for example:
```bash
docker compose build --no-cache --build-arg APT_MIRROR=http://mirrors.tuna.tsinghua.edu.cn/ubuntu/
```

## API
- `GET /healthz` - liveness check
- `POST /process` - primary endpoint (`input_type=gvhmr|smplx_npz`, comma-separated `output_formats`)
- `POST /render` - legacy endpoint (fixed to GVHMR `.pt`)

Dependency note: form uploads require `python-multipart` (included in Dockerfile and `setup.py`).

## Resolution and camera
- Default render size: `DEFAULT_WIDTH` / `DEFAULT_HEIGHT` in `app/main.py`.
- Override per request with `width` and `height`.
- Camera for video output in `app/main.py`:
  - Tracks robot base (`ROBOT_BASE_DICT[robot]`)
  - Distance from `VIEWER_CAM_DISTANCE_DICT[robot]`
  - Elevation `-10`
  - Azimuth `270`

## CLI test
```bash
python test_render.py --endpoint process --input_type gvhmr --pt hmr4d_results.pt --outputs mp4 --out out.mp4
python test_render.py --endpoint process --input_type smplx_npz --coord_fix yup_to_zup --pt smpl_input.npz --outputs mp4,csv --out out.zip
```
