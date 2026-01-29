import asyncio
import os
import tempfile
import uuid
from pathlib import Path

import imageio
import mujoco as mj
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from general_motion_retargeting import (
    GeneralMotionRetargeting as GMR,
    ROBOT_BASE_DICT,
    VIEWER_CAM_DISTANCE_DICT,
)
from general_motion_retargeting.utils.smpl import (
    get_gvhmr_data_offline_fast,
    load_gvhmr_pred_file,
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


def render_gvhmr_to_video(
    gvhmr_pred_file: Path,
    robot: str,
    smplx_model_dir: Path,
    output_path: Path,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
):
    """Convert GVHMR .pt prediction to robot video."""
    if not smplx_model_dir.exists():
        raise FileNotFoundError(
            f"SMPL-X model directory missing: {smplx_model_dir}. "
            "Place SMPLX_NEUTRAL.pkl etc. under assets/body_models/smplx/ or set SMPLX_MODEL_DIR."
        )

    smplx_data, body_model, smplx_output, actual_human_height = load_gvhmr_pred_file(
        gvhmr_pred_file, smplx_model_dir
    )
    smplx_data_frames, aligned_fps = get_gvhmr_data_offline_fast(
        smplx_data, body_model, smplx_output, tgt_fps=30
    )

    # Initialize retargeting
    retarget = GMR(
        actual_human_height=actual_human_height,
        src_human="smplx",
        tgt_robot=robot,
        verbose=False,
    )

    # Clamp to model offscreen framebuffer limits to avoid renderer errors
    max_offh = int(retarget.model.vis.global_.offheight)
    max_offw = int(retarget.model.vis.global_.offwidth)
    if max_offh > 0 and height > max_offh:
        height = max_offh
    if max_offw > 0 and width > max_offw:
        width = max_offw

    renderer = None
    # Camera roughly matches RobotMotionViewer front view
    camera = mj.MjvCamera()
    cam_opt = mj.MjvOption()
    mj.mjv_defaultCamera(camera)
    mj.mjv_defaultOption(cam_opt)
    camera.distance = VIEWER_CAM_DISTANCE_DICT[robot]
    camera.elevation = -10
    camera.azimuth = 270

    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = imageio.get_writer(output_path, fps=aligned_fps)

    renderer = mj.Renderer(retarget.model, height=height, width=width)

    try:
        for frame in smplx_data_frames:
            qpos = retarget.retarget(frame)
            # Update internal mujoco state
            retarget.configuration.data.qpos[:] = qpos
            mj.mj_forward(retarget.model, retarget.configuration.data)

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
        writer.close()

    return output_path


@app.get("/healthz")
async def healthz():
    return JSONResponse({"status": "ok"})


@app.post("/render")
async def render_endpoint(
    file: UploadFile = File(..., description="GVHMR .pt file"),
    robot: str = Form("unitree_g1"),
    width: int = Form(DEFAULT_WIDTH),
    height: int = Form(DEFAULT_HEIGHT),
):
    """Upload a GVHMR .pt file and get back an MP4 of the retargeted robot."""
    if not file.filename.endswith(".pt"):
        raise HTTPException(status_code=400, detail="Input must be a .pt file")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pt") as tmp:
        contents = await file.read()
        tmp.write(contents)
        tmp_path = Path(tmp.name)

    output_path = VIDEOS_DIR / f"{uuid.uuid4().hex}.mp4"

    try:
        path = await asyncio.get_event_loop().run_in_executor(
            None,
            render_gvhmr_to_video,
            tmp_path,
            robot,
            DEFAULT_SMPLX_DIR,
            output_path,
            width,
            height,
        )
    except Exception as e:
        # Clean up and surface a friendly error
        output_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        tmp_path.unlink(missing_ok=True)

    return FileResponse(
        path=path,
        media_type="video/mp4",
        filename=path.name,
    )


@app.get("/")
async def root():
    return JSONResponse(
        {
            "service": "GMR render",
            "upload_endpoint": "/render",
            "default_robot": "unitree_g1",
        }
    )
