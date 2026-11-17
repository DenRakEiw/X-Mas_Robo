"""Rendert Standbilder der Weihnachts-Szene nach out/ (zur Kontrolle ohne Fenster).

    .venv/Scripts/python sim/render_preview.py
"""
from pathlib import Path

import mujoco
from PIL import Image

ROOT = Path(__file__).parent.parent
model = mujoco.MjModel.from_xml_path(str(ROOT / "sim" / "g1" / "xmas_scene.xml"))
data = mujoco.MjData(model)
mujoco.mj_resetDataKeyframe(model, data, 0)
mujoco.mj_forward(model, data)

out = ROOT / "out"
out.mkdir(exist_ok=True)
with mujoco.Renderer(model, height=720, width=1280) as r:
    for cam in ("front", "wide", "orbit"):
        r.update_scene(data, camera=cam)
        Image.fromarray(r.render()).save(out / f"preview_{cam}.png")
        print("ok", cam)
