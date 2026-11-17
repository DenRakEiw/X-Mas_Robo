"""Der ganze Weg in einer Funktion: Link/Datei -> Pose -> G1-Bewegung -> Vergleichsvideo.

Wird vom Kommandozeilen-Skript dance.py und vom Server (server.py) benutzt.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).parent.parent
VIDEOS, MOTIONS, OUT = ROOT / "videos", ROOT / "motions", ROOT / "out"

STAGES = ("fetch", "pose", "retarget", "render")
Progress = Callable[[str, float], None]   # (Stufe, Anteil 0..1)


def safe_name(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "_", s).strip("_")
    return s[:60] or "dance"


def poster(video: Path, jpg: Path) -> None:
    import cv2
    cap = cv2.VideoCapture(str(video))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, n // 2))
    ok, frame = cap.read()
    cap.release()
    if ok:
        h, w = frame.shape[:2]
        frame = cv2.resize(frame, (int(w * 360 / h), 360), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(jpg), frame, [cv2.IMWRITE_JPEG_QUALITY, 82])


def run(source: str, name: str | None = None, max_seconds: float | None = None,
        camera: str = "dance", render_video: bool = True, on_progress: Progress | None = None) -> dict:
    import compose
    import motion
    import pose
    import retarget
    import video

    say = on_progress or (lambda stage, frac: None)
    step = lambda stage: (lambda i, n: say(stage, i / n if n else 0.0))
    t0 = time.perf_counter()

    say("fetch", 0.0)
    path, title = video.fetch(source, VIDEOS)
    name = safe_name(name or path.stem)

    say("pose", 0.0)
    track = pose.extract(path, max_seconds, step("pose"))

    say("retarget", 0.0)
    fps, qpos = retarget.retarget_track(track, step("retarget"))
    MOTIONS.mkdir(exist_ok=True)
    motion.save(MOTIONS / f"{name}.npz", fps, qpos)

    out = None
    if render_video:
        say("render", 0.0)
        out = compose.render(path, fps, qpos, OUT / f"{name}.mp4", camera, progress=step("render"))
        poster(out, OUT / f"{name}.jpg")

    meta = dict(
        name=name, title=title or path.stem, source=source if re.match(r"^https?://", source) else path.name,
        seconds=round(len(qpos) / fps, 1), fps=round(fps, 2), frames=len(qpos),
        detected=round(float(track.detected.mean()), 3), took=round(time.perf_counter() - t0, 1),
        created=time.strftime("%Y-%m-%d %H:%M"), video=f"{name}.mp4" if out else None)
    (MOTIONS / f"{name}.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    say("render", 1.0)
    return meta
