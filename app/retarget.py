"""Uebertraegt menschliche Koerperpunkte auf die Gelenke des Unitree G1.

Prinzip: Die Richtungen der menschlichen Gliedmassen (Oberarm, Unterarm, Oberschenkel,
Unterschenkel) und die Ausrichtung von Becken, Oberkoerper und Fuessen werden uebernommen,
die Laengen kommen vom Roboter. Geloest wird pro Bild mit gedaempfter Ausgleichsrechnung
(inverse Kinematik) auf dem MuJoCo-Modell, gestartet von der Loesung des vorigen Bildes.

Die Klasse Retargeter arbeitet Bild fuer Bild und ist damit auch fuer Live-Betrieb gedacht;
retarget_track() ist die Offline-Variante mit Glaettung und Fussverankerung.
"""
from __future__ import annotations

from pathlib import Path

import mujoco
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.spatial.transform import Rotation as R

from pose import (L_AN, L_EL, L_HEEL, L_HIP, L_KN, L_SH, L_TOE, L_WR, R_AN, R_EL, R_HEEL, R_HIP,
                  R_KN, R_SH, R_TOE, R_WR, PoseTrack)

G1_XML = Path(__file__).parent.parent / "sim" / "g1" / "g1.xml"

W_POS = 12.0     # Gewicht Positionsfehler (pro Meter)
W_TORSO = 1.5    # Gewicht Oberkoerper-Ausrichtung (pro Radiant)
W_FOOT = 0.5
W_REST = 0.03    # zieht alle Gelenke leicht zur Nullstellung
W_WRIST = 0.3    # Handgelenke haben keine Vorgabe, bleiben nahe Null
W_PREV = 0.08    # zieht zur Loesung des vorigen Bildes (Ruhe)
DAMP = 1e-3
MAX_SPEED = 14.0  # rad/s, begrenzt Spruenge bei gestreckten Armen/Beinen und Erkennungsfehlern
SOLE_R = 0.005


def _norm(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v) + 1e-9)


def _frame(y: np.ndarray, up: np.ndarray) -> np.ndarray:
    """Rotationsmatrix mit Spalten x (vorn), y (links), z (oben)."""
    y = _norm(y)
    x = _norm(np.cross(y, up))
    z = np.cross(x, y)
    return np.stack([x, y, z], axis=1)


def _smoothstep(v: float, lo: float, hi: float) -> float:
    t = float(np.clip((v - lo) / (hi - lo), 0, 1))
    return t * t * (3 - 2 * t)


class Retargeter:
    def __init__(self) -> None:
        self.m = mujoco.MjModel.from_xml_path(str(G1_XML))
        self.d = mujoco.MjData(self.m)
        self.nj = self.m.nu if self.m.nu == 29 else self.m.nv - 6
        b = lambda n: self.m.body(n).id
        self.torso = b("torso_link")
        self.side = {}
        for s in ("left", "right"):
            self.side[s] = dict(
                shoulder=b(f"{s}_shoulder_roll_link"), elbow=b(f"{s}_elbow_link"), wrist=b(f"{s}_wrist_yaw_link"),
                hip=b(f"{s}_hip_roll_link"), knee=b(f"{s}_knee_link"), foot=b(f"{s}_ankle_roll_link"))
        self.lo = self.m.jnt_range[1:, 0] + 0.02
        self.hi = self.m.jnt_range[1:, 1] - 0.02
        self.rest_w = np.full(self.nj, W_REST)
        for j in range(1, self.m.njnt):
            if "wrist" in self.m.joint(j).name:
                self.rest_w[j - 1] = W_WRIST

        # Laengen der Robotersegmente aus der Nullstellung
        mujoco.mj_resetData(self.m, self.d)
        self.d.qpos[:3] = 0
        mujoco.mj_kinematics(self.m, self.d)
        x = self.d.xpos
        self.len = {s: dict(
            upper=np.linalg.norm(x[c["elbow"]] - x[c["shoulder"]]), fore=np.linalg.norm(x[c["wrist"]] - x[c["elbow"]]),
            thigh=np.linalg.norm(x[c["knee"]] - x[c["hip"]]), shank=np.linalg.norm(x[c["foot"]] - x[c["knee"]]))
            for s, c in self.side.items()}
        # Sohlenpunkte im Koordinatensystem des Fusses
        self.sole = np.array([[-0.05, 0.025, -0.03], [-0.05, -0.025, -0.03], [0.12, 0.03, -0.03], [0.12, -0.03, -0.03]])
        self.q = np.zeros(self.nj)
        self.first = True
        self._jp = np.zeros((3, self.m.nv))
        self._jr = np.zeros((3, self.m.nv))

    # ---- Hilfen -----------------------------------------------------------
    def _jac(self, body: int) -> tuple[np.ndarray, np.ndarray]:
        mujoco.mj_jacBody(self.m, self.d, self._jp, self._jr, body)
        return self._jp[:, 6:].copy(), self._jr[:, 6:].copy()

    def _xmat(self, body: int) -> np.ndarray:
        return self.d.xmat[body].reshape(3, 3)

    def sole_points(self, s: str) -> np.ndarray:
        f = self.side[s]["foot"]
        return self.d.xpos[f] + self.sole @ self._xmat(f).T

    # ---- ein Bild ---------------------------------------------------------
    def solve(self, P: np.ndarray, vis: np.ndarray, flat_feet: tuple[bool, bool] = (False, False),
              dt: float = 1 / 30) -> np.ndarray:
        """P: (33,3) Punkte in Sim-Koordinaten. Rueckgabe qpos (36,) mit Basis im Ursprung."""
        up_w = np.array([0.0, 0.0, 1.0])
        hip_mid = 0.5 * (P[L_HIP] + P[R_HIP])
        sh_mid = 0.5 * (P[L_SH] + P[R_SH])
        spine = _norm(sh_mid - hip_mid)
        R_pelvis = _frame(P[L_HIP] - P[R_HIP], spine)
        # Becken nur zur Haelfte mit der Wirbelsaeule neigen, den Rest uebernimmt die Taille
        R_pelvis = _frame(R_pelvis[:, 1], _norm(spine + up_w))
        R_torso = _frame(P[L_SH] - P[R_SH], spine)

        quat = np.zeros(4)
        mujoco.mju_mat2Quat(quat, R_pelvis.flatten())
        self.d.qpos[:3] = 0
        self.d.qpos[3:7] = quat

        # Zielrichtungen, bei schlecht sichtbaren Gliedmassen zur Ruhehaltung ueberblendet
        down = -R_pelvis[:, 2]
        idx = {"left": (L_SH, L_EL, L_WR, L_HIP, L_KN, L_AN, L_HEEL, L_TOE), "right": (R_SH, R_EL, R_WR, R_HIP, R_KN, R_AN, R_HEEL, R_TOE)}
        tgt = {}
        for k, (s, (sh, el, wr, hp, kn, an, heel, toe)) in enumerate(idx.items()):
            a_arm = _smoothstep(min(vis[el], vis[wr]), 0.25, 0.6)
            a_leg = _smoothstep(min(vis[kn], vis[an]), 0.25, 0.6)
            rest_arm = -R_torso[:, 2]
            fwd = R_pelvis[:, 0]
            foot_x = _norm(P[toe] - P[heel])
            foot_x = _norm(a_leg * foot_x + (1 - a_leg) * fwd)
            if flat_feet[k]:
                foot_x = _norm(foot_x * np.array([1, 1, 0]))
            tgt[s] = dict(
                upper=_norm(a_arm * _norm(P[el] - P[sh]) + (1 - a_arm) * rest_arm),
                fore=_norm(a_arm * _norm(P[wr] - P[el]) + (1 - a_arm) * rest_arm),
                thigh=_norm(a_leg * _norm(P[kn] - P[hp]) + (1 - a_leg) * down),
                shank=_norm(a_leg * _norm(P[an] - P[kn]) + (1 - a_leg) * down),
                foot=_frame(np.cross(up_w, foot_x), np.cross(foot_x, np.cross(up_w, foot_x))))

        q_prev = self.q.copy()
        for _ in range(40 if self.first else 8):
            self.d.qpos[7:7 + self.nj] = self.q
            mujoco.mj_kinematics(self.m, self.d)
            mujoco.mj_comPos(self.m, self.d)
            x = self.d.xpos
            rows, errs = [], []

            _, jr = self._jac(self.torso)
            errs.append(W_TORSO * R.from_matrix(R_torso @ self._xmat(self.torso).T).as_rotvec())
            rows.append(W_TORSO * jr)

            for s, c in self.side.items():
                jac = {n: self._jac(c[n]) for n in ("shoulder", "elbow", "wrist", "hip", "knee", "foot")}
                L, t = self.len[s], tgt[s]
                for a, b_, key in (("shoulder", "elbow", "upper"), ("elbow", "wrist", "fore"), ("hip", "knee", "thigh"), ("knee", "foot", "shank")):
                    errs.append(W_POS * (t[key] * L[key] - (x[c[b_]] - x[c[a]])))
                    rows.append(W_POS * (jac[b_][0] - jac[a][0]))
                errs.append(W_FOOT * R.from_matrix(t["foot"] @ self._xmat(c["foot"]).T).as_rotvec())
                rows.append(W_FOOT * jac["foot"][1])

            errs.append(-self.rest_w * self.q)
            rows.append(np.diag(self.rest_w))
            if not self.first:
                errs.append(W_PREV * (q_prev - self.q))
                rows.append(W_PREV * np.eye(self.nj))

            J = np.vstack(rows)
            e = np.concatenate(errs)
            dq = np.linalg.solve(J.T @ J + DAMP * np.eye(self.nj), J.T @ e)
            self.q = np.clip(self.q + dq, self.lo, self.hi)
            if not self.first:
                self.q = np.clip(self.q, q_prev - MAX_SPEED * dt, q_prev + MAX_SPEED * dt)

        self.first = False
        self.d.qpos[7:7 + self.nj] = self.q
        mujoco.mj_kinematics(self.m, self.d)
        return self.d.qpos[:36].copy()


def _fill_gaps(a: np.ndarray, ok: np.ndarray) -> np.ndarray:
    """Luecken (nicht erkannte Bilder) linear ueberbruecken."""
    if ok.all():
        return a
    t = np.arange(len(a))
    flat = a.reshape(len(a), -1).copy()
    for c in range(flat.shape[1]):
        flat[~ok, c] = np.interp(t[~ok], t[ok], flat[ok, c])
    return flat.reshape(a.shape)


def _level(world: np.ndarray) -> np.ndarray:
    """Gleicht eine nach oben oder unten gekippte Kamera aus (hoechstens 25 Grad)."""
    spine = 0.5 * (world[:, L_SH] + world[:, R_SH]) - 0.5 * (world[:, L_HIP] + world[:, R_HIP])
    m = np.median(spine, axis=0)
    ang = float(np.clip(np.arctan2(m[0], m[2]), -np.radians(25), np.radians(25)))
    rot = R.from_euler("y", -ang).as_matrix()
    return world @ rot.T


def retarget_track(track: PoseTrack, progress=None, stage_radius: float = 1.9) -> tuple[float, np.ndarray]:
    if track.detected.sum() < 5:
        raise RuntimeError("Im Video wurde kaum eine Person erkannt")
    fps = track.fps
    world = _fill_gaps(track.world, track.detected)
    vis = _fill_gaps(track.vis, track.detected)
    world = _level(world)
    world = gaussian_filter1d(world, sigma=max(0.8, fps * 0.045), axis=0, mode="nearest")
    vis = gaussian_filter1d(vis, sigma=fps * 0.15, axis=0, mode="nearest")

    rt = Retargeter()
    T = len(world)
    qpos = np.zeros((T, 36))
    soles = np.zeros((T, 2, 4, 3))
    for i in range(T):
        qpos[i] = rt.solve(world[i], vis[i], dt=1 / fps)
        soles[i, 0], soles[i, 1] = rt.sole_points("left"), rt.sole_points("right")
        if progress and i % 30 == 0:
            progress(i, T)

    # Zweiter Durchgang fuer Standfuesse: wer nahe am Boden ist, steht flach
    low = soles[..., 2].min(axis=2)                 # (T, 2) tiefster Sohlenpunkt je Fuss
    ground = low.min(axis=1, keepdims=True)
    near = (low - ground) < 0.03
    rt2 = Retargeter()
    for i in range(T):
        qpos[i] = rt2.solve(world[i], vis[i], flat_feet=(bool(near[i, 0]), bool(near[i, 1])), dt=1 / fps)
        soles[i, 0], soles[i, 1] = rt2.sole_points("left"), rt2.sole_points("right")

    qpos[:, 7:] = gaussian_filter1d(qpos[:, 7:], sigma=max(0.6, fps * 0.03), axis=0, mode="nearest")

    # Hoehe: tiefster Sohlenpunkt steht auf dem Boden
    low = soles[..., 2].min(axis=2)
    z = -(low.min(axis=1) - SOLE_R)
    qpos[:, 2] = gaussian_filter1d(z, sigma=max(0.6, fps * 0.04), mode="nearest")

    # Standfuss-Verankerung: der tiefere Fuss bleibt am Ort, das Becken bewegt sich darueber
    centers = soles[..., :2].mean(axis=2)           # (T, 2, 2) Fussmitte relativ zum Becken
    xy = np.zeros((T, 2))
    sup = int(np.argmin(low[0]))
    anchor = centers[0, sup].copy()
    for i in range(T):
        other = 1 - sup
        if low[i, other] < low[i, sup] - 0.02:      # Wechsel mit etwas Hysterese
            anchor = xy[i - 1] + centers[i, other] if i else centers[i, other].copy()
            sup = other
        xy[i] = anchor - centers[i, sup]
    # langsames Wegdriften entfernen, Schritte bleiben erhalten
    xy -= gaussian_filter1d(xy, sigma=fps * 2.5, axis=0, mode="nearest")
    xy = gaussian_filter1d(xy, sigma=max(0.6, fps * 0.04), axis=0, mode="nearest")
    r = np.linalg.norm(xy, axis=1, keepdims=True)
    xy *= np.minimum(1.0, stage_radius / np.maximum(r, 1e-6))
    qpos[:, :2] = xy
    return fps, qpos
