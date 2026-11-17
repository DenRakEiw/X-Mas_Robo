"""Exportiert Szene, Roboter und Demo-Bewegungen fuer die Browser-Version nach web/assets/.

Quelle ist das kompilierte MuJoCo-Modell (sim/g1/xmas_scene.xml), damit Browser und
lokale App dieselbe Welt und denselben Roboter zeigen.

    .venv/Scripts/python sim/build_xmas_scene.py
    .venv/Scripts/python tools/export_web.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import mujoco
import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "sim"))
import motion  # noqa: E402

OUT = ROOT / "web" / "assets"
TYPES = {0: "plane", 2: "sphere", 3: "capsule", 4: "ellipsoid", 5: "cylinder", 6: "box", 7: "mesh"}
r = lambda a, n=5: [round(float(v), n) for v in np.asarray(a).ravel()]


def main() -> None:
    m = mujoco.MjModel.from_xml_path(str(ROOT / "sim" / "g1" / "xmas_scene.xml"))
    d = mujoco.MjData(m)
    mujoco.mj_resetDataKeyframe(m, d, 0)
    stand = d.qpos.copy()
    mujoco.mj_forward(m, d)

    blob = bytearray()
    meshes: dict[int, dict] = {}

    def mesh_ref(mid: int) -> int:
        if mid not in meshes:
            va, vn = m.mesh_vertadr[mid], m.mesh_vertnum[mid]
            fa, fn = m.mesh_faceadr[mid], m.mesh_facenum[mid]
            v = m.mesh_vert[va:va + vn].astype("<f4")
            f = m.mesh_face[fa:fa + fn].astype("<u4")
            meshes[mid] = dict(id=len(meshes), vert=[len(blob), int(vn)], face=[len(blob) + v.nbytes, int(fn)])
            blob.extend(v.tobytes())
            blob.extend(f.tobytes())
        return meshes[mid]["id"]

    def material(g: int) -> dict:
        mat = m.geom_matid[g]
        if mat < 0:
            return dict(name="", rgba=r(m.geom_rgba[g], 3), emission=0, specular=0.5, shininess=0.5, reflectance=0)
        return dict(name=m.material(mat).name, rgba=r(m.mat_rgba[mat], 3), emission=round(float(m.mat_emission[mat]), 3),
                    specular=round(float(m.mat_specular[mat]), 3), shininess=round(float(m.mat_shininess[mat]), 3),
                    reflectance=round(float(m.mat_reflectance[mat]), 3))

    # ---- Roboter: Koerperbaum mit Gelenken und sichtbaren Meshes
    robot_ids = [b for b in range(m.nbody) if m.body_rootid[b] == 1]
    index = {b: i for i, b in enumerate(robot_ids)}
    bodies = []
    for b in robot_ids:
        body = dict(name=m.body(b).name, parent=index.get(int(m.body_parentid[b]), -1),
                    pos=r(m.body_pos[b]), quat=r(m.body_quat[b], 6), geoms=[])
        j = m.body_jntadr[b]
        if j >= 0 and m.jnt_type[j] == mujoco.mjtJoint.mjJNT_HINGE:
            body["joint"] = dict(name=m.joint(j).name, index=int(m.jnt_qposadr[j]) - 7, axis=r(m.jnt_axis[j]), range=r(m.jnt_range[j], 4))
        for g in range(m.ngeom):
            if m.geom_bodyid[g] == b and m.geom_group[g] == 2 and m.geom_type[g] == 7:
                body["geoms"].append(dict(mesh=mesh_ref(int(m.geom_dataid[g])), pos=r(m.geom_pos[g]), quat=r(m.geom_quat[g], 6),
                                          rgba=material(g)["rgba"]))
        bodies.append(body)

    # ---- Welt: alle uebrigen Geoms mit Weltlage, nach Material gruppierbar
    mats: dict[str, int] = {}
    mat_list: list[dict] = []
    geoms = []
    quat = np.zeros(4)
    for g in range(m.ngeom):
        if m.body_rootid[m.geom_bodyid[g]] == 1:
            continue
        mat = material(g)
        key = json.dumps(mat, sort_keys=True)
        if key not in mats:
            mats[key] = len(mat_list)
            mat_list.append(mat)
        mujoco.mju_mat2Quat(quat, d.geom_xmat[g])
        item = dict(type=TYPES[int(m.geom_type[g])], size=r(m.geom_size[g], 4), pos=r(d.geom_xpos[g], 4), quat=r(quat, 5),
                    mat=mats[key], name=m.geom(g).name)
        if item["type"] == "mesh":
            item["mesh"] = mesh_ref(int(m.geom_dataid[g]))
        geoms.append(item)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "meshes.bin").write_bytes(bytes(blob))
    scene = dict(
        robot=dict(bodies=bodies, stand=r(stand, 4)),
        world=dict(geoms=geoms, materials=mat_list),
        meshes=sorted(meshes.values(), key=lambda x: x["id"]),
    )
    (OUT / "scene.json").write_text(json.dumps(scene, separators=(",", ":")), encoding="utf-8")
    print(f"scene.json: {len(bodies)} Koerper, {len(geoms)} Welt-Geoms, {len(meshes)} Meshes; meshes.bin {len(blob) / 1e6:.1f} MB")

    # ---- Demo-Bewegungen
    (OUT / "motions").mkdir(exist_ok=True)
    demos = {"test_dance": motion.make_test_dance(seconds=16.0)}
    kathak = ROOT / "motions" / "kathak.npz"
    if kathak.exists():
        demos["kathak"] = motion.load(kathak)
    for name, (fps, q) in demos.items():
        data = dict(fps=round(float(fps), 4), frames=len(q), qpos=r(q, 4))
        (OUT / "motions" / f"{name}.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        print(f"motions/{name}.json: {len(q)} Bilder")


if __name__ == "__main__":
    main()
