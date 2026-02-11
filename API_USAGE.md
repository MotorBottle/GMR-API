# GMR API Usage

This service exposes two endpoints:
- `/process` (recommended)
- `/render` (legacy compatibility, fixed `input_type=gvhmr`)

## Base URL
- Local: `http://localhost:8000`
- Docker compose: `http://localhost:8000`

## Endpoints
- `GET /healthz`
- `POST /process`
- `POST /render` (legacy)

## `POST /process`
`multipart/form-data` fields:
- `file` (required): input motion file
- `input_type` (optional): `gvhmr` (default) or `smplx_npz`
- `coord_fix` (optional): `none` (default) or `yup_to_zup` (for `smplx_npz`)
- `robot` (optional): target robot, default `unitree_g1`
- `output_formats` (optional): comma-separated outputs, default `mp4`
- `return_format` (optional, legacy fallback): single output value if `output_formats` is absent
- `width` (optional): render width for video output
- `height` (optional): render height for video output

Input file requirements:
- `input_type=gvhmr` -> `.pt`
- `input_type=smplx_npz` -> `.npz`
- `coord_fix=yup_to_zup` is supported for `smplx_npz` only

## `POST /render` (legacy)
`multipart/form-data` fields:
- `file` (required): GVHMR `.pt`
- `robot` (optional): target robot
- `output_formats` (optional): comma-separated outputs
- `return_format` (optional, legacy fallback): single output value
- `width` (optional): video width
- `height` (optional): video height

## Output Selection
Use `output_formats` as comma-separated values from:
- `mp4`
- `traj`
- `csv`

Examples:
- `output_formats=mp4`
- `output_formats=csv,traj`
- `output_formats=mp4,csv,traj`

Response behavior:
- one output -> returns that file directly
- multiple outputs -> returns `.zip` containing requested files

## Output Definitions
- `mp4`: video file (`video/mp4`)
- `traj`: pickle file (`application/octet-stream`) with keys:
  - `fps`
  - `root_pos` (`N x 3`)
  - `root_rot` (`N x 4`, `xyzw`)
  - `dof_pos` (`N x D`)
  - `local_body_pos`
  - `link_body_list`
- `csv`: `text/csv`, columns:
  - `[x, y, z, qx, qy, qz, qw, joint_1, ..., joint_29]`
  - currently restricted to `robot=unitree_g1` for mjlab compatibility

## PowerShell Examples
Single CSV output (GVHMR):
```powershell
& "$env:WINDIR\System32\curl.exe" -X POST "http://localhost:8000/process" `
  -F "input_type=gvhmr" `
  -F "robot=unitree_g1" `
  -F "output_formats=csv" `
  -F "file=@hmr4d_results.pt" `
  -o out.csv
```

SMPL-X NPZ input test:
```powershell
& "$env:WINDIR\System32\curl.exe" -X POST "http://localhost:8000/process" `
  -F "input_type=smplx_npz" `
  -F "coord_fix=yup_to_zup" `
  -F "robot=unitree_g1" `
  -F "output_formats=mp4,csv" `
  -F "file=@smpl_input.npz" `
  -o out.zip
```

Legacy endpoint:
```powershell
& "$env:WINDIR\System32\curl.exe" -X POST "http://localhost:8000/render" `
  -F "robot=unitree_g1" `
  -F "output_formats=mp4" `
  -F "file=@hmr4d_results.pt" `
  -o out.mp4
```

## CLI Helper
`test_render.py` supports both endpoints and comma-separated outputs:
```bash
python test_render.py --endpoint process --input_type gvhmr --pt hmr4d_results.pt --outputs mp4
python test_render.py --endpoint process --input_type smplx_npz --coord_fix yup_to_zup --pt smpl_input.npz --outputs mp4,csv --out out.zip
python test_render.py --endpoint render --pt hmr4d_results.pt --outputs csv --out out.csv
```
