"""Rendert das Vergleichsvideo: links das Original, rechts der G1 in der Weihnachts-Szene, mit Ton."""
from __future__ import annotations

import subprocess
from pathlib import Path

import cv2
import imageio.v2 as imageio
import imageio_ffmpeg
import mujoco
import numpy as np

from play import SCENE, Snow, frame_at


def render(video: Path, fps: float, qpos: np.ndarray, out: Path, camera: str = "dance",
           height: int = 720, sim_width: int = 1280, progress=None) -> Path:
    model = mujoco.MjModel.from_xml_path(str(SCENE))
    data = mujoco.MjData(model)
    cap = cv2.VideoCapture(str(video))
    vw, vh = cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    left_w = int(round(height * vw / vh / 2)) * 2
    snow = Snow()
    n = len(qpos)
    silent = out.with_name(out.stem + "_silent.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)

    with mujoco.Renderer(model, height=height, width=sim_width) as r, \
            imageio.get_writer(silent, fps=fps, quality=8, macro_block_size=2) as w:
        for i in range(n):
            ok, frame = cap.read()
            if not ok:
                break
            left = cv2.cvtColor(cv2.resize(frame, (left_w, height), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
            data.qpos[:] = frame_at(qpos, fps, i / fps, loop=False)
            mujoco.mj_forward(model, data)
            snow.step(1 / fps, i / fps)
            r.update_scene(data, camera=camera)
            r.scene.ngeom = snow.draw(r.scene, r.scene.ngeom)
            w.append_data(np.hstack([left, r.render()]))
            if progress and i % 30 == 0:
                progress(i, n)
    cap.release()

    # Ton des Originals dazumischen; hat das Video keinen Ton, bleibt es stumm
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ff, "-y", "-loglevel", "error", "-i", str(silent), "-i", str(video),
           "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "copy", "-c:a", "aac", "-shortest", str(out)]
    if subprocess.run(cmd).returncode == 0 and out.exists():
        silent.unlink()
    else:
        silent.replace(out)
    return out
