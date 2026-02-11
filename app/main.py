import asyncio
import os
import pickle
import tempfile
import uuid
import zipfile
from pathlib import Path

import imageio
import mujoco as mj
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from scipy.spatial.transform import Rotation as R

from general_motion_retargeting import (
    GeneralMotionRetargeting as GMR,
    ROBOT_BASE_DICT,
    VIEWER_CAM_DISTANCE_DICT,
)
from general_motion_retargeting.utils.smpl import (
    get_gvhmr_data_offline_fast,
    get_smplx_data_offline_fast,
    load_gvhmr_pred_file,
    load_smplx_file,
)

# Default locations
ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SMPLX_DIR = Path(
    os.getenv("SMPLX_MODEL_DIR", ROOT_DIR / "assets" / "body_models")
)
VIDEOS_DIR = ROOT_DIR / "videos"

# Render defaults
DEFAULT_WIDTH = 540
DEFAULT_HEIGHT = 960

# Prefer headless rendering
os.environ.setdefault("MUJOCO_GL", "osmesa")

app = FastAPI(title="GMR Render Service", version="0.1.0")


def _cleanup_generated_files(output_stem: Path) -> None:
    for p in output_stem.parent.glob(f"{output_stem.name}*"):
        if p.suffix in {".mp4", ".pkl", ".csv", ".zip"}:
            p.unlink(missing_ok=True)


def _parse_output_formats(output_formats: str | None, return_format: str | None) -> list[str]:
    allowed = {"mp4", "traj", "csv"}
    raw = output_formats if output_formats else (return_format if return_format else "mp4")
    tokens = [token.strip().lower() for token in raw.split(",") if token.strip()]
    expanded = []
    for token in tokens:
        if token == "both":
            expanded.extend(["mp4", "traj"])
        else:
            expanded.append(token)
    # Deduplicate while preserving order
    seen = set()
    formats = []
    for token in expanded:
        if token not in seen:
            seen.add(token)
            formats.append(token)
    if not formats:
        raise ValueError("No valid output format provided")
    invalid = [token for token in formats if token not in allowed]
    if invalid:
        raise ValueError(f"Invalid output formats: {','.join(invalid)}")
    return formats


def _load_input_frames(
    input_file: Path,
    input_type: str,
    smplx_model_dir: Path,
    tgt_fps: int = 30,
):
    input_type = input_type.lower()
    if input_type == "gvhmr":
        smplx_data, body_model, smplx_output, actual_human_height = load_gvhmr_pred_file(
            input_file, smplx_model_dir
        )
        smplx_data_frames, aligned_fps = get_gvhmr_data_offline_fast(
            smplx_data, body_model, smplx_output, tgt_fps=tgt_fps
        )
    elif input_type in ("smplx_npz", "smplx"):
        smplx_data, body_model, smplx_output, actual_human_height = load_smplx_file(
            input_file, smplx_model_dir
        )
        smplx_data_frames, aligned_fps = get_smplx_data_offline_fast(
            smplx_data, body_model, smplx_output, tgt_fps=tgt_fps
        )
    else:
        raise ValueError(
            "unsupported input_type. Currently supported: gvhmr, smplx_npz"
        )
    return smplx_data_frames, aligned_fps, actual_human_height


def _validate_input_extension(input_type: str, filename: str) -> None:
    input_type = input_type.lower()
    if input_type == "gvhmr" and not filename.endswith(".pt"):
        raise ValueError("Input must be a .pt file for input_type=gvhmr")
    elif input_type in ("smplx_npz", "smplx") and not filename.endswith(".npz"):
        raise ValueError("Input must be a .npz file for input_type=smplx_npz")
    elif input_type not in ("gvhmr", "smplx_npz", "smplx"):
        raise ValueError("unsupported input_type. Currently supported: gvhmr, smplx_npz")


def _validate_coord_fix(input_type: str, coord_fix: str) -> None:
    allowed = {"none", "yup_to_zup"}
    if coord_fix not in allowed:
        raise ValueError("coord_fix must be one of: none, yup_to_zup")
    if input_type == "gvhmr" and coord_fix != "none":
        raise ValueError("coord_fix is only supported for smplx_npz input")


def _apply_coord_fix_to_frames(smplx_data_frames: list[dict], coord_fix: str) -> list[dict]:
    if coord_fix == "none":
        return smplx_data_frames

    # Match the existing gvhmr correction used in get_gvhmr_data_offline_fast.
    rotation_matrix = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], dtype=np.float64)
    rot_fix = R.from_matrix(rotation_matrix)

    fixed_frames = []
    for frame in smplx_data_frames:
        fixed_frame = {}
        for joint_name, (pos, quat_wxyz) in frame.items():
            pos_np = np.asarray(pos)
            quat_np = np.asarray(quat_wxyz)
            pos_fixed = pos_np @ rotation_matrix.T
            quat_fixed = (rot_fix * R.from_quat(quat_np, scalar_first=True)).as_quat(
                scalar_first=True
            )
            fixed_frame[joint_name] = (pos_fixed, quat_fixed)
        fixed_frames.append(fixed_frame)
    return fixed_frames


def process_motion_input(
    input_file: Path,
    input_type: str,
    robot: str,
    smplx_model_dir: Path,
    output_stem: Path,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    output_formats: list[str] | None = None,
    coord_fix: str = "none",
):
    """Convert input motion file to robot video and/or trajectory/csv."""
    if not smplx_model_dir.exists():
        raise FileNotFoundError(
            f"SMPL-X model directory missing: {smplx_model_dir}. "
            "Place SMPLX_NEUTRAL.pkl etc. under assets/body_models/smplx/ or set SMPLX_MODEL_DIR."
        )

    if output_formats is None:
        output_formats = ["mp4"]
    _validate_coord_fix(input_type, coord_fix)

    smplx_data_frames, aligned_fps, actual_human_height = _load_input_frames(
        input_file=input_file,
        input_type=input_type,
        smplx_model_dir=smplx_model_dir,
        tgt_fps=30,
    )
    if input_type in ("smplx_npz", "smplx"):
        smplx_data_frames = _apply_coord_fix_to_frames(smplx_data_frames, coord_fix)

    # Initialize retargeting
    retarget = GMR(
        actual_human_height=actual_human_height,
        src_human="smplx",
        tgt_robot=robot,
        verbose=False,
    )

    output_stem.parent.mkdir(parents=True, exist_ok=True)
    qpos_list = []
    writer = None
    renderer = None
    camera = None
    cam_opt = None
    mp4_path = output_stem.with_suffix(".mp4")
    traj_path = output_stem.with_suffix(".pkl")
    csv_path = output_stem.with_suffix(".csv")
    need_video = "mp4" in output_formats
    need_traj = "traj" in output_formats
    need_csv = "csv" in output_formats
    need_qpos = need_traj or need_csv

    # Only set up rendering resources when returning mp4
    if need_video:
        # Clamp to model offscreen framebuffer limits to avoid renderer errors
        max_offh = int(retarget.model.vis.global_.offheight)
        max_offw = int(retarget.model.vis.global_.offwidth)
        if max_offh > 0 and height > max_offh:
            height = max_offh
        if max_offw > 0 and width > max_offw:
            width = max_offw

        # Camera roughly matches RobotMotionViewer front view
        camera = mj.MjvCamera()
        cam_opt = mj.MjvOption()
        mj.mjv_defaultCamera(camera)
        mj.mjv_defaultOption(cam_opt)
        camera.distance = VIEWER_CAM_DISTANCE_DICT[robot]
        camera.elevation = -10
        camera.azimuth = 270

        writer = imageio.get_writer(mp4_path, fps=aligned_fps)
        renderer = mj.Renderer(retarget.model, height=height, width=width)

    try:
        for frame in smplx_data_frames:
            qpos = retarget.retarget(frame)
            if need_qpos:
                qpos_list.append(qpos.copy())
            # Update internal mujoco state
            retarget.configuration.data.qpos[:] = qpos
            mj.mj_forward(retarget.model, retarget.configuration.data)

            if need_video:
                # lock camera on robot base
                robot_base = ROBOT_BASE_DICT[robot]
                camera.lookat[:] = retarget.configuration.data.xpos[
                    retarget.model.body(robot_base).id
                ]

                renderer.update_scene(
                    retarget.configuration.data, camera=camera, scene_option=cam_opt
                )
                img = renderer.render()
                writer.append_data(img)
    finally:
        try:
            if renderer is not None:
                renderer.close()
        except Exception:
            pass
        if writer is not None:
            writer.close()

    if need_qpos:
        import numpy as np

        qpos_array = np.asarray(qpos_list)
        root_pos = qpos_array[:, :3]
        root_rot_wxyz = qpos_array[:, 3:7]
        root_rot_xyzw = root_rot_wxyz[:, [1, 2, 3, 0]]
        dof_pos = qpos_array[:, 7:]

    if need_traj:
        motion_data = {
            "fps": aligned_fps,
            "root_pos": root_pos,
            "root_rot": root_rot_xyzw,
            "dof_pos": dof_pos,
            "local_body_pos": None,
            "link_body_list": None,
        }
        with open(traj_path, "wb") as f:
            pickle.dump(motion_data, f)

    if need_csv:
        # mjlab motion imitation csv_to_npz currently expects Unitree G1 29-DoF layout.
        if robot != "unitree_g1":
            raise ValueError(
                "csv export for mjlab is currently supported only for robot='unitree_g1'"
            )
        if dof_pos.shape[1] != 29:
            raise ValueError(
                f"csv export expected 29 joint DoF for unitree_g1, got {dof_pos.shape[1]}"
            )
        csv_data = np.concatenate([root_pos, root_rot_xyzw, dof_pos], axis=1)
        np.savetxt(csv_path, csv_data, delimiter=",", fmt="%.8f")

    return {
        "mp4": mp4_path if need_video else None,
        "traj": traj_path if need_traj else None,
        "csv": csv_path if need_csv else None,
    }


def _build_file_response_for_formats(
    result: dict[str, Path | None],
    formats: list[str],
    output_stem: Path,
):
    if len(formats) == 1:
        fmt = formats[0]
        chosen = result[fmt]
        if chosen is None:
            raise ValueError(f"Requested output format '{fmt}' was not generated")
        if fmt == "mp4":
            media_type = "video/mp4"
        elif fmt == "traj":
            media_type = "application/octet-stream"
        else:
            media_type = "text/csv"
        return FileResponse(path=chosen, media_type=media_type, filename=chosen.name)

    zip_path = output_stem.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fmt in formats:
            p = result.get(fmt)
            if p is not None:
                zf.write(p, arcname=p.name)
    return FileResponse(path=zip_path, media_type="application/zip", filename=zip_path.name)


@app.get("/healthz")
async def healthz():
    return JSONResponse({"status": "ok"})


@app.post("/render")
async def render_endpoint(
    file: UploadFile = File(..., description="GVHMR .pt file"),
    robot: str = Form("unitree_g1"),
    width: int = Form(DEFAULT_WIDTH),
    height: int = Form(DEFAULT_HEIGHT),
    output_formats: str | None = Form(None),
    return_format: str | None = Form("mp4"),
    coord_fix: str = Form("none"),
):
    """Legacy endpoint: fixed gvhmr input, returns one or more outputs."""
    try:
        _validate_input_extension("gvhmr", file.filename)
        formats = _parse_output_formats(output_formats, return_format)
        _validate_coord_fix("gvhmr", coord_fix)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pt") as tmp:
        contents = await file.read()
        tmp.write(contents)
        tmp_path = Path(tmp.name)

    output_stem = VIDEOS_DIR / uuid.uuid4().hex

    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            process_motion_input,
            tmp_path,
            "gvhmr",
            robot,
            DEFAULT_SMPLX_DIR,
            output_stem,
            width,
            height,
            formats,
            coord_fix,
        )
    except ValueError as e:
        _cleanup_generated_files(output_stem)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Clean up and surface a friendly error
        _cleanup_generated_files(output_stem)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        tmp_path.unlink(missing_ok=True)

    return _build_file_response_for_formats(result, formats, output_stem)


@app.post("/process")
async def process_endpoint(
    file: UploadFile = File(..., description="Input motion file"),
    input_type: str = Form("gvhmr"),
    robot: str = Form("unitree_g1"),
    width: int = Form(DEFAULT_WIDTH),
    height: int = Form(DEFAULT_HEIGHT),
    output_formats: str | None = Form(None),
    return_format: str | None = Form("mp4"),
    coord_fix: str = Form("none"),
):
    """Main endpoint: supports input routing and comma-separated output selection."""
    input_type = input_type.lower()
    try:
        _validate_input_extension(input_type, file.filename)
        formats = _parse_output_formats(output_formats, return_format)
        _validate_coord_fix(input_type, coord_fix)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    suffix = ".pt" if input_type == "gvhmr" else ".npz"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)

    output_stem = VIDEOS_DIR / uuid.uuid4().hex
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            process_motion_input,
            tmp_path,
            input_type,
            robot,
            DEFAULT_SMPLX_DIR,
            output_stem,
            width,
            height,
            formats,
            coord_fix,
        )
    except ValueError as e:
        _cleanup_generated_files(output_stem)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        _cleanup_generated_files(output_stem)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        tmp_path.unlink(missing_ok=True)

    return _build_file_response_for_formats(result, formats, output_stem)


@app.get("/")
async def root():
    return JSONResponse(
        {
            "service": "GMR render",
            "upload_endpoint": "/process",
            "legacy_upload_endpoint": "/render",
            "default_robot": "unitree_g1",
        }
    )
