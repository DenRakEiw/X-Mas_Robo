"""Spielt eine Bewegung auf dem G1 in der Weihnachts-Szene ab (kinematisch, in Echtzeit).

    .venv/Scripts/python sim/play.py                         # Test-Tanz im Fenster
    .venv/Scripts/python sim/play.py motions/xyz.npz         # eigene Bewegung
    .venv/Scripts/python sim/play.py --video out/dance.mp4   # statt Fenster als mp4 rendern

Im Fenster: Maus dreht/zoomt, Leertaste pausiert, [ und ] wechseln die Kamera.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import mujoco
import numpy as np

import motion as motion_lib

ROOT = Path(__file__).parent.parent
SCENE = ROOT / "sim" / "g1" / "xmas_scene.xml"
N_FLAKES = 220


class Snow:
    """Fallende Schneeflocken als Zusatz-Geoms in der Szene (keine Physik)."""

    def __init__(self, seed: int = 0):
        self.rng = np.random.default_rng(seed)
        self.pos = self.rng.uniform([-7, -7, 0], [6, 7, 7], size=(N_FLAKES, 3))
        self.size = self.rng.uniform(0.012, 0.03, N_FLAKES)
        self.speed = self.rng.uniform(0.35, 0.8, N_FLAKES)
        self.phase = self.rng.uniform(0, 6.28, N_FLAKES)

    def step(self, dt: float, t: float) -> None:
        self.pos[:, 2] -= self.speed * dt
        self.pos[:, 0] += 0.15 * np.sin(t * 0.9 + self.phase) * dt
        self.pos[:, 1] += 0.15 * np.cos(t * 0.7 + self.phase) * dt
        low = self.pos[:, 2] < 0
        self.pos[low, 2] = 7.0

    def draw(self, scn: mujoco.MjvScene, start: int) -> int:
        rgba = np.array([1, 1, 1, 0.95], dtype=np.float32)
        eye = np.eye(3).flatten()
        n = start
        for p, s in zip(self.pos, self.size):
            if n >= scn.maxgeom:
                break
            mujoco.mjv_initGeom(scn.geoms[n], mujoco.mjtGeom.mjGEOM_SPHERE, np.array([s, 0, 0]), p, eye, rgba)
            scn.geoms[n].emission = 0.9
            n += 1
        return n


def frame_at(qpos: np.ndarray, fps: float, t: float, loop: bool) -> np.ndarray:
    f = t * fps
    last = len(qpos) - 1
    f = f % last if loop else min(f, last)
    i = int(f)
    a = f - i
    q0, q1 = qpos[i], qpos[min(i + 1, last)]
    q = (1 - a) * q0 + a * q1
    quat = q[3:7]
    q[3:7] = quat / np.linalg.norm(quat)
    return q


def run_window(model, data, fps, qpos, seconds: float | None, loop: bool) -> None:
    import mujoco.viewer

    snow = Snow()
    paused = False
    cam_ids = [-1] + list(range(model.ncam))
    cam_idx = [1]

    def on_key(key: int) -> None:
        nonlocal paused
        if key == 32:
            paused = not paused
        elif key in (ord("["), ord("]")):
            cam_idx[0] = (cam_idx[0] + (1 if key == ord("]") else -1)) % len(cam_ids)
            cam_idx.append(-999)  # Markierung: Kamera neu setzen

    with mujoco.viewer.launch_passive(model, data, key_callback=on_key, show_left_ui=False, show_right_ui=False) as viewer:
        def set_cam() -> None:
            cid = cam_ids[cam_idx[0]]
            if cid < 0:
                viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
            else:
                viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
                viewer.cam.fixedcamid = cid

        set_cam()
        t = 0.0
        wall = time.perf_counter()
        start = wall
        while viewer.is_running():
            now = time.perf_counter()
            dt, wall = now - wall, now
            if seconds is not None and now - start > seconds:
                break
            if len(cam_idx) > 1:
                del cam_idx[1:]
                set_cam()
            if not paused:
                t += dt
                snow.step(dt, t)
            data.qpos[:] = frame_at(qpos, fps, t, loop)
            mujoco.mj_forward(model, data)
            with viewer.lock():
                viewer.user_scn.ngeom = snow.draw(viewer.user_scn, 0)
            viewer.sync()
            time.sleep(max(0.0, 1 / 60 - (time.perf_counter() - now)))


def run_video(model, data, fps, qpos, out: Path, camera: str, width: int, height: int) -> None:
    import imageio.v2 as imageio

    out.parent.mkdir(parents=True, exist_ok=True)
    snow = Snow()
    vfps = 30
    n = int((len(qpos) - 1) / fps * vfps)
    with mujoco.Renderer(model, height=height, width=width) as r, imageio.get_writer(out, fps=vfps, quality=8) as w:
        for i in range(n):
            t = i / vfps
            data.qpos[:] = frame_at(qpos, fps, t, loop=False)
            mujoco.mj_forward(model, data)
            snow.step(1 / vfps, t)
            r.update_scene(data, camera=camera)
            r.scene.ngeom = snow.draw(r.scene, r.scene.ngeom)
            w.append_data(r.render())
    print(f"geschrieben: {out}  ({n} Frames)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("motion", nargs="?", help=".npz-Bewegung; ohne Angabe laeuft der Test-Tanz")
    ap.add_argument("--video", type=Path, help="als mp4 rendern statt Fenster oeffnen")
    ap.add_argument("--camera", default="orbit", help="Kamera fuer --video: front, wide, orbit")
    ap.add_argument("--size", default="1280x720")
    ap.add_argument("--seconds", type=float, help="Fenster nach so vielen Sekunden schliessen")
    ap.add_argument("--no-loop", action="store_true")
    args = ap.parse_args()

    fps, qpos = motion_lib.load(args.motion) if args.motion else motion_lib.make_test_dance()
    model = mujoco.MjModel.from_xml_path(str(SCENE))
    data = mujoco.MjData(model)

    if args.video:
        w, h = (int(v) for v in args.size.split("x"))
        run_video(model, data, fps, qpos, args.video, args.camera, w, h)
    else:
        run_window(model, data, fps, qpos, args.seconds, loop=not args.no_loop)


if __name__ == "__main__":
    main()
