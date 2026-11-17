"""Pose-Erkennung Bild fuer Bild mit MediaPipe Pose Landmarker.

Liefert 33 Koerperpunkte pro Bild als 3D-Koordinaten in Metern, bereits im
Koordinatensystem der Simulation: x nach vorn (zur Kamera), y nach links, z nach oben,
Ursprung in der Hueftmitte.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

MODEL = Path(__file__).parent.parent / "models" / "pose_landmarker_heavy.task"

# MediaPipe-Indizes
NOSE = 0
L_SH, R_SH, L_EL, R_EL, L_WR, R_WR = 11, 12, 13, 14, 15, 16
L_HIP, R_HIP, L_KN, R_KN, L_AN, R_AN = 23, 24, 25, 26, 27, 28
L_HEEL, R_HEEL, L_TOE, R_TOE = 29, 30, 31, 32


@dataclass
class PoseTrack:
    fps: float
    world: np.ndarray   # (T, 33, 3) Sim-Koordinaten, NaN wo nichts erkannt wurde
    vis: np.ndarray     # (T, 33) Sichtbarkeit 0..1
    image: np.ndarray   # (T, 33, 2) normierte Bildkoordinaten (x rechts, y unten)
    detected: np.ndarray  # (T,) bool


def mp_to_sim(p: np.ndarray) -> np.ndarray:
    """MediaPipe-Welt (x rechts, y unten, z von der Kamera weg) -> Sim (x vor, y links, z oben)."""
    return np.stack([-p[..., 2], p[..., 0], -p[..., 1]], axis=-1)


def make_landmarker(mode=vision.RunningMode.VIDEO) -> vision.PoseLandmarker:
    opts = vision.PoseLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(MODEL)),
        running_mode=mode,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return vision.PoseLandmarker.create_from_options(opts)


def extract(video: Path, max_seconds: float | None = None, progress=None) -> PoseTrack:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Video laesst sich nicht oeffnen: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    if max_seconds:
        total = min(total, int(max_seconds * fps)) if total else int(max_seconds * fps)

    world, vis, image, detected = [], [], [], []
    with make_landmarker() as lm:
        i = 0
        while True:
            ok, frame = cap.read()
            if not ok or (max_seconds and i >= max_seconds * fps):
                break
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = lm.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), int(i * 1000 / fps))
            if res.pose_world_landmarks:
                w = res.pose_world_landmarks[0]
                n = res.pose_landmarks[0]
                world.append(mp_to_sim(np.array([[p.x, p.y, p.z] for p in w])))
                vis.append(np.array([p.visibility for p in w]))
                image.append(np.array([[p.x, p.y] for p in n]))
                detected.append(True)
            else:
                world.append(np.full((33, 3), np.nan))
                vis.append(np.zeros(33))
                image.append(np.full((33, 2), np.nan))
                detected.append(False)
            i += 1
            if progress and i % 15 == 0:
                progress(i, total)
    cap.release()
    if not world:
        raise RuntimeError("Video enthaelt keine Bilder")
    return PoseTrack(fps, np.array(world), np.array(vis), np.array(image), np.array(detected))
