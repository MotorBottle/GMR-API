# GMR API Usage

FastAPI service for yanjieze/GMR, now supports gvhmr and smplx(z-up and y-up).

## SMPL-X models (required)
1. Register / log in at https://smpl-x.is.tue.mpg.de/download.php
2. Download SMPL-X v1.1 “NPZ+PKL” package.
3. Place the model files as:
   ```
   assets/body_models/smplx/SMPLX_NEUTRAL.pkl
   assets/body_models/smplx/SMPLX_FEMALE.pkl
   assets/body_models/smplx/SMPLX_MALE.pkl
   ```
4. No config change is needed; the API and scripts look in `assets/body_models`.

## Quick Start (Local)
```bash
# create env
conda create -n GMR python=3.10 -y
conda activate GMR

# install package + deps
pip install -e .
conda install -c conda-forge libstdcxx-ng -y
pip install fastapi uvicorn[standard] python-multipart

# run server
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Quick Start (Docker)
```bash
docker compose up -d --build
```
Volumes:
- `./assets/body_models` -> `/app/assets/body_models` (SMPL-X models, read-only)
- `./videos` -> `/app/videos` (outputs)

Set `MUJOCO_GL=osmesa` (default) for headless; use `egl` + NVIDIA block for GPU.

## Endpoints
- `GET /healthz`
- `POST /process` (recommended)
- `POST /render` (legacy, use if you know how; fixed `input_type=gvhmr`)

## What the API does
- Accepts motion inputs (`gvhmr` .pt or `smplx_npz` .npz).
- Retargets to the chosen robot using GMR.
- Outputs any combination of:
  - `mp4` (rendered video)
  - `traj` (pickle with qpos and metadata)
  - `csv` (mjlab-compatible, currently `robot=unitree_g1` only)
- Multiple outputs are bundled into a zip; single output is returned directly.

## /process
- `file` (required): motion file
- `input_type` (default `gvhmr`; also `smplx_npz`)
- `coord_fix` (`none` | `yup_to_zup`, only for `smplx_npz`)
- `robot` (default `unitree_g1`)
- `output_formats` (comma-separated; default `mp4`; options `mp4`, `traj`, `csv`)
- `return_format` (legacy single-value fallback)
- `width`, `height` (video)

File requirements:
- `gvhmr` -> `.pt`
- `smplx_npz` -> `.npz`

Output behavior:
- One output -> direct file
- Multiple outputs -> zip of requested files

Outputs:
- `mp4`: video
- `traj`: pickle with `fps`, `root_pos`, `root_rot (xyzw)`, `dof_pos`, `local_body_pos`, `link_body_list`
- `csv`: `[x,y,z,qx,qy,qz,qw,joint...]`, currently only `robot=unitree_g1`

## /render (legacy)
- Same fields but fixed to `input_type=gvhmr`; `coord_fix` must be `none`.

## Examples (PowerShell with curl.exe)
GVHMR -> CSV:
```powershell
& "$env:WINDIR\System32\curl.exe" -X POST "http://localhost:8000/process" `
  -F "input_type=gvhmr" -F "robot=unitree_g1" -F "output_formats=csv" `
  -F "file=@hmr4d_results.pt" -o out.csv
```

SMPL-X NPZ -> MP4+CSV (zip):
```powershell
& "$env:WINDIR\System32\curl.exe" -X POST "http://localhost:8000/process" `
  -F "input_type=smplx_npz" -F "coord_fix=yup_to_zup" `
  -F "robot=unitree_g1" -F "output_formats=mp4,csv" `
  -F "file=@smpl_input.npz" -o out.zip
```

Legacy render:
```powershell
& "$env:WINDIR\System32\curl.exe" -X POST "http://localhost:8000/render" `
  -F "robot=unitree_g1" -F "output_formats=mp4" `
  -F "file=@hmr4d_results.pt" -o out.mp4
```

## CLI helper
```bash
python test_render.py --endpoint process --input_type gvhmr --pt hmr4d_results.pt --outputs mp4
python test_render.py --endpoint process --input_type smplx_npz --coord_fix yup_to_zup --pt smpl_input.npz --outputs mp4,csv --out out.zip
python test_render.py --endpoint render --pt hmr4d_results.pt --outputs csv --out out.csv
```
