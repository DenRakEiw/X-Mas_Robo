"""Bewegungsformat und Test-Tanz fuer den G1.

Eine Bewegung ist eine .npz-Datei mit
    fps   : float
    qpos  : (T, 36) = Basis-Position xyz, Basis-Quaternion wxyz, 29 Gelenkwinkel
            in der Reihenfolge des MuJoCo-Modells sim/g1/g1.xml.
Die spaetere Pipeline (Video -> Pose -> Retargeting) schreibt genau dieses Format.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

# Gelenk-Indizes innerhalb der 29 Gelenke
L_HIP_P, L_HIP_R, L_HIP_Y, L_KNEE, L_ANK_P, L_ANK_R = range(0, 6)
R_HIP_P, R_HIP_R, R_HIP_Y, R_KNEE, R_ANK_P, R_ANK_R = range(6, 12)
WAIST_Y, WAIST_R, WAIST_P = range(12, 15)
L_SH_P, L_SH_R, L_SH_Y, L_ELB = range(15, 19)
R_SH_P, R_SH_R, R_SH_Y, R_ELB = range(22, 26)

STAND_Z = 0.79
LEG = 0.60  # Oberschenkel + Unterschenkel, grob


def load(path: str | Path) -> tuple[float, np.ndarray]:
    d = np.load(path)
    qpos = np.asarray(d["qpos"], dtype=np.float64)
    if qpos.ndim != 2 or qpos.shape[1] != 36:
        raise ValueError(f"{path}: qpos muss (T, 36) sein, ist {qpos.shape}")
    return float(d["fps"]), qpos


def save(path: str | Path, fps: float, qpos: np.ndarray) -> None:
    np.savez_compressed(path, fps=np.float64(fps), qpos=qpos)


def make_test_dance(seconds: float = 16.0, fps: float = 50.0, bpm: float = 120.0) -> tuple[float, np.ndarray]:
    """Einfacher prozeduraler Tanz, nur um Szene und Player ohne Video zu testen."""
    n = int(seconds * fps)
    t = np.arange(n) / fps
    beat = 2 * np.pi * bpm / 60.0 * t      # eine Periode pro Schlag
    half = beat / 2                         # eine Periode pro zwei Schlaege
    q = np.zeros((n, 36))

    # Kniebeuge im Takt, Huefte gleicht aus, Basis sinkt entsprechend
    bend = 0.22 + 0.16 * (0.5 - 0.5 * np.cos(beat))
    sway = 0.10 * np.sin(half)              # Gewicht von Bein zu Bein
    j = q[:, 7:]
    for hp, hr, kn, ap, ar in ((L_HIP_P, L_HIP_R, L_KNEE, L_ANK_P, L_ANK_R), (R_HIP_P, R_HIP_R, R_KNEE, R_ANK_P, R_ANK_R)):
        j[:, hp] = -bend
        j[:, kn] = 2 * bend
        j[:, ap] = -bend
        j[:, hr] = sway
        j[:, ar] = -sway
    q[:, 0] = 0.0
    q[:, 1] = -LEG * np.sin(sway) * 0.9
    q[:, 2] = STAND_Z - LEG * (1 - np.cos(bend)) - 0.005

    # Oberkoerper dreht und wippt
    j[:, WAIST_Y] = 0.35 * np.sin(half)
    j[:, WAIST_R] = 0.08 * np.sin(half + 0.6)

    # Arme: erste Haelfte seitliches Winken, zweite Haelfte abwechselnd nach oben
    phase = (t % 8.0) < 4.0
    wave = np.sin(beat)
    j[:, L_SH_R] = np.where(phase, 1.15 + 0.25 * wave, 0.35)
    j[:, R_SH_R] = np.where(phase, -1.15 + 0.25 * wave, -0.35)
    j[:, L_SH_P] = np.where(phase, 0.0, -1.6 - 0.9 * np.sin(half))
    j[:, R_SH_P] = np.where(phase, 0.0, -1.6 + 0.9 * np.sin(half))
    j[:, L_ELB] = np.where(phase, 0.55 + 0.45 * wave, 0.5)
    j[:, R_ELB] = np.where(phase, 0.55 - 0.45 * wave, 0.5)

    # harte Umschaltung der Armfiguren glaetten
    k = int(fps * 0.3) | 1
    kernel = np.hanning(k + 2)[1:-1]
    kernel /= kernel.sum()
    for c in range(15, 29):
        j[:, c] = np.convolve(np.pad(j[:, c], k // 2, mode="edge"), kernel, mode="valid")

    q[:, 3] = 1.0  # Basis aufrecht, Blick Richtung +x zur Kamera
    return fps, q


if __name__ == "__main__":
    out = Path(__file__).parent.parent / "motions"
    out.mkdir(exist_ok=True)
    fps, q = make_test_dance()
    save(out / "test_dance.npz", fps, q)
    print(f"geschrieben: {out / 'test_dance.npz'}  ({len(q)} Frames, {fps:.0f} fps)")
