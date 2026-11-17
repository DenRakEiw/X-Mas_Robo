"""Erzeugt die Weihnachts-Location als MuJoCo-Szene (sim/g1/xmas_scene.xml).

Alles ist prozedural aus Primitiven und Inline-Meshes gebaut, es werden keine
externen 3D-Assets gebraucht. Deko-Geoms kollidieren nicht (contype/conaffinity 0),
nur Boden und Buehne sind fest.

    .venv/Scripts/python sim/build_xmas_scene.py
"""
from __future__ import annotations

import math
import random
from pathlib import Path

OUT = Path(__file__).parent / "g1" / "xmas_scene.xml"
rng = random.Random(24)

DECO = 'contype="0" conaffinity="0"'
geoms: list[str] = []


def g(s: str) -> None:
    geoms.append("    " + s)


def cone_vertices(n: int = 20) -> str:
    """Einheitskegel: Grundkreis Radius 1 bei z=0, Spitze bei z=1."""
    pts = [(math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n), 0.0) for i in range(n)]
    pts.append((0.0, 0.0, 1.0))
    return "  ".join(f"{x:.4f} {y:.4f} {z:.4f}" for x, y, z in pts)


def star_vertices() -> str:
    """Flacher fuenfzackiger Stern wird als konvexe Huelle zum Fuenfeck, daher Doppelpyramide."""
    pts = [(0, 0.03, 0), (0, -0.03, 0)]
    for i in range(5):
        a = math.pi / 2 + 2 * math.pi * i / 5
        pts.append((math.cos(a), 0, math.sin(a)))
    return "  ".join(f"{x:.4f} {y:.4f} {z:.4f}" for x, y, z in pts)


def tree(x: float, y: float, h: float, decorated: bool = False, name: str = "") -> None:
    r = h * 0.30
    trunk_h = h * 0.14
    g(f'<geom type="cylinder" pos="{x:.3f} {y:.3f} {trunk_h / 2:.3f}" size="{h * 0.045:.3f} {trunk_h / 2:.3f}" material="bark" {DECO}/>')
    tiers = 4 if decorated else 3
    z = trunk_h
    for i in range(tiers):
        f = 1 - i / (tiers + 0.6)
        tier_r = r * f
        tier_h = h * 0.86 / tiers * 1.55
        mat = "fir" if i % 2 == 0 else "fir2"
        g(f'<geom type="mesh" mesh="cone_{_cone_class(tier_r, tier_h)}" pos="{x:.3f} {y:.3f} {z:.3f}" '
          f'material="{mat}" {DECO}/>')
        # Schneekappe am unteren Rand jeder Etage
        g(f'<geom type="cylinder" pos="{x:.3f} {y:.3f} {z + 0.004:.3f}" size="{tier_r * 1.02:.3f} 0.006" material="snowcap" {DECO}/>')
        if decorated:
            n = max(5, int(14 * f))
            for k in range(n):
                a = 2 * math.pi * k / n + i * 0.7
                t = 0.18 + 0.5 * rng.random()  # Hoehe entlang der Etage
                rr = tier_r * (1 - t) * 1.0
                col = rng.choice(["orn_red", "orn_white"])
                g(f'<geom type="sphere" pos="{x + rr * math.cos(a):.3f} {y + rr * math.sin(a):.3f} {z + tier_h * t:.3f}" '
                  f'size="{0.045 if rng.random() < 0.6 else 0.03}" material="{col}" {DECO}/>')
        z += tier_h * 0.52
    if decorated:
        top = z + h * 0.86 / tiers * 1.55 * 0.48
        g(f'<geom type="mesh" mesh="star" pos="{x:.3f} {y:.3f} {top + 0.16:.3f}" material="star" {DECO}/>')
        g(f'<light pos="{x:.3f} {y - 0.4:.3f} {top + 0.3:.3f}" dir="0 0.3 -1" diffuse="1.0 0.30 0.52" specular="0.2 0.1 0.15" '
          f'attenuation="0.4 0.1 0.03" castshadow="false"/>')


_cone_classes: dict[tuple[float, float], str] = {}


def _cone_class(r: float, h: float) -> str:
    key = (round(r, 3), round(h, 3))
    if key not in _cone_classes:
        _cone_classes[key] = f"c{len(_cone_classes)}"
    return _cone_classes[key]


def present(x: float, y: float, s: float, yaw: float, mat: str, ribbon: str) -> None:
    h = s * rng.uniform(0.7, 1.2)
    q = f"{math.cos(yaw / 2):.4f} 0 0 {math.sin(yaw / 2):.4f}"
    g(f'<body pos="{x:.3f} {y:.3f} {h:.3f}" quat="{q}">'
      f'<geom type="box" size="{s:.3f} {s:.3f} {h:.3f}" material="{mat}" {DECO}/>'
      f'<geom type="box" size="{s * 1.01:.3f} {s * 0.16:.3f} {h * 1.01:.3f}" material="{ribbon}" {DECO}/>'
      f'<geom type="box" size="{s * 0.16:.3f} {s * 1.01:.3f} {h * 1.01:.3f}" material="{ribbon}" {DECO}/>'
      f'<geom type="sphere" pos="0 0 {h + s * 0.12:.3f}" size="{s * 0.22:.3f}" material="{ribbon}" {DECO}/>'
      f'</body>')


def snowman(x: float, y: float, yaw: float) -> None:
    q = f"{math.cos(yaw / 2):.4f} 0 0 {math.sin(yaw / 2):.4f}"
    g(f'<body pos="{x:.3f} {y:.3f} 0" quat="{q}">'
      f'<geom type="sphere" pos="0 0 0.36" size="0.40" material="snowball" {DECO}/>'
      f'<geom type="sphere" pos="0 0 0.92" size="0.29" material="snowball" {DECO}/>'
      f'<geom type="sphere" pos="0 0 1.34" size="0.20" material="snowball" {DECO}/>'
      # Augen, Nase, Knoepfe
      f'<geom type="sphere" pos="0.175 0.07 1.39" size="0.025" material="coal" {DECO}/>'
      f'<geom type="sphere" pos="0.175 -0.07 1.39" size="0.025" material="coal" {DECO}/>'
      f'<geom type="capsule" fromto="0.18 0 1.33 0.36 0 1.32" size="0.028" material="carrot" {DECO}/>'
      f'<geom type="sphere" pos="0.285 0 1.00" size="0.03" material="coal" {DECO}/>'
      f'<geom type="sphere" pos="0.29 0 0.88" size="0.03" material="coal" {DECO}/>'
      # Schal und Zylinder
      f'<geom type="cylinder" pos="0 0 1.17" size="0.19 0.035" material="present_red" {DECO}/>'
      f'<geom type="box" pos="0.12 0.14 1.05" size="0.03 0.05 0.13" material="present_red" {DECO}/>'
      f'<geom type="cylinder" pos="0 0 1.52" size="0.24 0.012" material="coal" {DECO}/>'
      f'<geom type="cylinder" pos="0 0 1.63" size="0.15 0.11" material="coal" {DECO}/>'
      f'<geom type="cylinder" pos="0 0 1.55" size="0.155 0.025" material="present_red" {DECO}/>'
      # Arme
      f'<geom type="capsule" fromto="0 0.26 0.98 0.1 0.62 1.25" size="0.018" material="bark" {DECO}/>'
      f'<geom type="capsule" fromto="0 -0.26 0.98 0.1 -0.62 1.25" size="0.018" material="bark" {DECO}/>'
      f'</body>')


def candy_cane(x: float, y: float, yaw: float, h: float = 1.3) -> None:
    """Stange plus Bogen aus kurzen, abwechselnd rot/weissen Kapseln."""
    pts = []
    n_straight = 9
    for i in range(n_straight + 1):
        pts.append((0.0, h * 0.78 * i / n_straight))
    r = h * 0.14
    for i in range(1, 9):
        a = math.pi * i / 8 * 0.95
        pts.append((r - r * math.cos(a), h * 0.78 + r * math.sin(a)))
    c, s = math.cos(yaw), math.sin(yaw)
    for i in range(len(pts) - 1):
        (u0, z0), (u1, z1) = pts[i], pts[i + 1]
        mat = "cane_red" if i % 2 == 0 else "cane_white"
        g(f'<geom type="capsule" fromto="{x + u0 * c:.3f} {y + u0 * s:.3f} {z0:.3f} {x + u1 * c:.3f} {y + u1 * s:.3f} {z1:.3f}" '
          f'size="0.045" material="{mat}" {DECO}/>')


def light_string(p0, p1, sag: float, n: int = 14) -> None:
    cols = ["bulb_warm", "bulb_red", "bulb_warm"]
    prev = None
    for i in range(n + 1):
        t = i / n
        x = p0[0] + (p1[0] - p0[0]) * t
        y = p0[1] + (p1[1] - p0[1]) * t
        z = p0[2] + (p1[2] - p0[2]) * t - sag * 4 * t * (1 - t)
        if prev:
            g(f'<geom type="capsule" fromto="{prev[0]:.3f} {prev[1]:.3f} {prev[2]:.3f} {x:.3f} {y:.3f} {z:.3f}" size="0.006" material="coal" {DECO}/>')
        if 0 < i < n:
            g(f'<geom type="sphere" pos="{x:.3f} {y:.3f} {z - 0.04:.3f}" size="0.045" material="{cols[i % len(cols)]}" {DECO}/>')
        prev = (x, y, z)


def cabin(x: float, y: float, yaw: float) -> None:
    q = f"{math.cos(yaw / 2):.4f} 0 0 {math.sin(yaw / 2):.4f}"
    w, d, h = 2.2, 1.6, 1.25
    parts = [f'<geom type="box" pos="0 0 {h}" size="{w} {d} {h}" material="wood" {DECO}/>']
    # Satteldach aus zwei geneigten Platten plus Schnee
    ang = math.radians(32)
    half = d / math.cos(ang) + 0.25
    for sgn in (1, -1):
        qy = f"{math.cos(sgn * ang / 2):.4f} {math.sin(sgn * ang / 2):.4f} 0 0"
        cy = -sgn * d / 2 * 1.0
        cz = 2 * h + d * math.tan(ang) / 2
        parts.append(f'<geom type="box" pos="0 {cy:.3f} {cz:.3f}" quat="{qy}" size="{w + 0.25} {half / 2 + 0.1:.3f} 0.07" material="roof" {DECO}/>')
        parts.append(f'<geom type="box" pos="0 {cy:.3f} {cz + 0.1:.3f}" quat="{qy}" size="{w + 0.28} {half / 2 + 0.12:.3f} 0.05" material="snow_soft" {DECO}/>')
    # Giebelfuellung
    parts.append(f'<geom type="box" pos="{w - 0.02} 0 {2 * h + 0.3}" size="0.03 {d * 0.55} 0.32" material="wood" {DECO}/>')
    # Tuer und leuchtende Fenster auf der Frontseite (+x)
    parts.append(f'<geom type="box" pos="{w + 0.01} 0 0.75" size="0.03 0.38 0.75" material="door" {DECO}/>')
    parts.append(f'<geom type="sphere" pos="{w + 0.05} 0.25 0.75" size="0.04" material="orn_gold" {DECO}/>')
    for wy in (-1.0, 1.0):
        parts.append(f'<geom type="box" pos="{w + 0.01} {wy} 1.45" size="0.03 0.34 0.34" material="window" {DECO}/>')
        parts.append(f'<geom type="box" pos="{w + 0.03} {wy} 1.45" size="0.02 0.36 0.025" material="wood_dark" {DECO}/>')
        parts.append(f'<geom type="box" pos="{w + 0.03} {wy} 1.45" size="0.02 0.025 0.36" material="wood_dark" {DECO}/>')
    # Kranz ueber der Tuer
    for k in range(12):
        a = 2 * math.pi * k / 12
        parts.append(f'<geom type="sphere" pos="{w + 0.06} {0.17 * math.cos(a):.3f} {1.78 + 0.17 * math.sin(a):.3f}" size="0.06" material="fir" {DECO}/>')
    parts.append(f'<geom type="sphere" pos="{w + 0.11} 0 1.61" size="0.045" material="orn_red" {DECO}/>')
    # Schornstein
    parts.append(f'<geom type="box" pos="-1.1 0.55 {2 * h + 0.75}" size="0.24 0.24 0.55" material="brick" {DECO}/>')
    parts.append(f'<geom type="box" pos="-1.1 0.55 {2 * h + 1.33}" size="0.28 0.28 0.05" material="snow_soft" {DECO}/>')
    parts.append(f'<light pos="{w + 1.2} 0 1.6" dir="1 0 -0.5" diffuse="0.9 0.25 0.45" specular="0.1 0.05 0.08" attenuation="0.3 0.15 0.05" castshadow="false"/>')
    g(f'<body pos="{x:.3f} {y:.3f} 0" quat="{q}">' + "".join(parts) + "</body>")


GLYPHS = {
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "G": ["01111", "10000", "10000", "10111", "10001", "10001", "01110"],
    "/": ["00001", "00001", "00010", "00100", "00100", "01000", "10000"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
}


def neon_sign(text: str, x: float, y_center: float, z0: float, px: float = 0.13) -> None:
    """Pixel-Schriftzug aus leuchtenden Wuerfeln, lesbar von +x aus (y waechst nach rechts)."""
    width = (len(text) * 6 - 1) * px
    y0 = y_center - width / 2
    for ci, ch in enumerate(text):
        for row, bits in enumerate(GLYPHS[ch]):
            for col, bit in enumerate(bits):
                if bit == "1":
                    y = y0 + (ci * 6 + col + 0.5) * px
                    z = z0 + (6 - row + 0.5) * px
                    g(f'<geom type="box" pos="{x:.3f} {y:.3f} {z:.3f}" size="0.04 {px * 0.47:.3f} {px * 0.47:.3f}" material="neon" {DECO}/>')
    # Traeger und pinke Unterlinie
    for yy in (y0 + 0.3, y0 + width - 0.3):
        g(f'<geom type="cylinder" pos="{x - 0.06:.3f} {yy:.3f} {z0 / 2:.3f}" size="0.03 {z0 / 2:.3f}" material="wood_dark" {DECO}/>')
    g(f'<geom type="box" pos="{x:.3f} {y_center:.3f} {z0 - 0.16:.3f}" size="0.03 {width / 2:.3f} 0.022" material="bulb_red" {DECO}/>')
    g(f'<light pos="{x + 1.2:.3f} {y_center:.3f} {z0 + 0.5:.3f}" dir="-1 0 -0.2" diffuse="0.5 0.5 0.55" specular="0 0 0" '
      f'attenuation="0.5 0.2 0.08" castshadow="false"/>')


SIGN = dict(x=-3.0, y=0.0, z0=1.9)


def build() -> str:
    # --- Buehne: runde, leicht spiegelnde Holzplattform mit Lichterrand
    stage_r = 2.6
    g(f'<geom name="stage" type="cylinder" pos="0 0 -0.02" size="{stage_r} 0.02" material="stage"/>')
    g(f'<geom type="cylinder" pos="0 0 -0.035" size="{stage_r + 0.14} 0.03" material="cane_red" {DECO}/>')
    n = 36
    for i in range(n):
        a = 2 * math.pi * i / n
        mat = ["bulb_warm", "bulb_red"][i % 2]
        g(f'<geom type="sphere" pos="{(stage_r + 0.07) * math.cos(a):.3f} {(stage_r + 0.07) * math.sin(a):.3f} 0.02" size="0.05" material="{mat}" {DECO}/>')

    # --- Grosser geschmueckter Baum hinter der Buehne (Kamera schaut Richtung -x)
    tree(-4.6, 0.0, 5.2, decorated=True)
    for (px, py, s, mat, rib) in [(-3.5, 0.9, 0.26, "present_red", "cane_white"), (-3.3, -0.2, 0.2, "present_green", "present_red"),
                                  (-3.6, -1.1, 0.3, "present_blue", "present_red"), (-3.0, 0.5, 0.15, "present_gold", "cane_white"),
                                  (-3.15, -0.9, 0.17, "present_red", "present_green"), (-3.9, 1.7, 0.22, "present_green", "cane_white")]:
        present(px, py, s, rng.uniform(0, 1.5), mat, rib)

    # --- Tannenwald im Halbkreis und darueber hinaus
    for i in range(46):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(6.5, 17)
        x, y = r * math.cos(a), r * math.sin(a)
        if x > 3.5 and abs(y) < 5:      # Blick der Hauptkamera freihalten
            continue
        if math.hypot(x + 6.5, y - 4.6) < 3.2:   # Platz fuer die Huette
            continue
        if -8.5 < x < -1.0 and -7.0 < y < -1.2:  # Platz und freie Sicht fuer die Leuchtschrift
            continue
        tree(x, y, rng.uniform(2.2, 4.8))

    cabin(-6.5, 4.6, math.radians(-38))
    neon_sign("IMAG/NE", SIGN["x"], SIGN["y"], SIGN["z0"])
    snowman(0.3, -4.1, math.radians(60))
    candy_cane(-1.2, 3.35, math.radians(-60))
    candy_cane(-2.75, 2.25, math.radians(-30), h=1.1)
    candy_cane(1.9, -3.4, math.radians(120), h=1.1)

    # --- Lichterketten zwischen vier Pfosten rund um die Buehne
    posts = [(-3.3, 3.3), (-3.3, -3.3), (3.3, -3.3), (3.3, 3.3)]
    ph = 2.9
    for (px, py) in posts:
        g(f'<geom type="cylinder" pos="{px} {py} {ph / 2}" size="0.05 {ph / 2}" material="wood_dark" {DECO}/>')
        g(f'<geom type="sphere" pos="{px} {py} {ph + 0.05}" size="0.11" material="bulb_warm" {DECO}/>')
    for i in range(4):
        a, b = posts[i], posts[(i + 1) % 4]
        if i in (0, 3):  # vorn zur Kamera offen, hinten haengt die Leuchtschrift
            continue
        light_string((a[0], a[1], ph), (b[0], b[1], ph), sag=0.55, n=18)
    light_string((posts[0][0], posts[0][1], ph), (-4.6, 0.6, 3.6), sag=0.3, n=8)
    light_string((posts[1][0], posts[1][1], ph), (-4.6, -0.6, 3.6), sag=0.3, n=8)

    # --- Schneehuegel und Schneeflocken in der Luft
    for _ in range(26):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(4.2, 15)
        s = rng.uniform(0.6, 2.2)
        g(f'<geom type="ellipsoid" pos="{r * math.cos(a):.3f} {r * math.sin(a):.3f} {-s * 0.12:.3f}" size="{s:.3f} {s * rng.uniform(0.7, 1.2):.3f} {s * 0.3:.3f}" material="snow_soft" {DECO}/>')
    for i in range(170):
        x, y, z = rng.uniform(-8, 6), rng.uniform(-7, 7), rng.uniform(0.2, 6.5)
        if math.hypot(x, y) < 1.0 and z < 2.2:
            continue
        g(f'<geom type="sphere" pos="{x:.3f} {y:.3f} {z:.3f}" size="{rng.uniform(0.012, 0.028):.3f}" material="flake" {DECO}/>')

    # Kegel-Etagen als skalierte Meshes: je Groesse ein eigenes Mesh
    cone_meshes = "\n".join(
        f'    <mesh name="cone_{cls}" vertex="{cone_vertices()}" scale="{r} {r} {h}"/>'
        for (r, h), cls in _cone_classes.items())
    body = "\n".join(geoms)

    return f"""<mujoco model="g1 xmas scene">
  <!-- Generiert von sim/build_xmas_scene.py, nicht von Hand bearbeiten -->
  <include file="g1.xml"/>

  <statistic center="0 0 0.9" extent="3.2"/>

  <visual>
    <headlight diffuse="0.17 0.17 0.18" ambient="0.20 0.20 0.21" specular="0 0 0"/>
    <rgba haze="0.03 0.03 0.035 1" fog="0.03 0.03 0.035 1"/>
    <global azimuth="180" elevation="-12" offwidth="1920" offheight="1080"/>
    <quality shadowsize="8192" offsamples="8"/>
    <map fogstart="14" fogend="38" zfar="60" shadowclip="1.5"/>
  </visual>

  <asset>
    <texture type="skybox" builtin="gradient" rgb1="0 0 0" rgb2="0.045 0.045 0.05" mark="random" markrgb="1 1 0.92" random="0.004" width="1024" height="6144"/>
    <texture type="2d" name="snow" builtin="flat" rgb1="0.84 0.84 0.87" mark="random" markrgb="1 1 1" random="0.06" width="512" height="512"/>
    <texture type="2d" name="planks" builtin="checker" rgb1="0.035 0.035 0.04" rgb2="0.07 0.07 0.075" mark="edge" markrgb="0.16 0.16 0.17" width="256" height="256"/>
    <material name="snow" texture="snow" texuniform="true" texrepeat="3 3" specular="0.25" shininess="0.3"/>
    <material name="snow_soft" rgba="0.80 0.80 0.83 1" specular="0.15" shininess="0.2"/>
    <material name="snowcap" rgba="0.95 0.95 0.97 1" specular="0.1"/>
    <material name="snowball" rgba="0.96 0.96 0.98 1" specular="0.2" shininess="0.3"/>
    <material name="flake" rgba="1 1 1 0.9" emission="0.8"/>
    <material name="stage" texture="planks" texuniform="true" texrepeat="2.5 2.5" reflectance="0.38" specular="0.7" shininess="0.8"/>
    <material name="fir" rgba="0.085 0.085 0.095 1" specular="0.25" shininess="0.4"/>
    <material name="fir2" rgba="0.13 0.13 0.14 1" specular="0.25" shininess="0.4"/>
    <material name="bark" rgba="0.05 0.05 0.05 1" specular="0.05"/>
    <material name="wood" rgba="0.11 0.11 0.12 1" specular="0.2"/>
    <material name="wood_dark" rgba="0.04 0.04 0.04 1" specular="0.2"/>
    <material name="roof" rgba="0.03 0.03 0.03 1"/>
    <material name="brick" rgba="0.16 0.16 0.17 1"/>
    <material name="door" rgba="0.91 0.20 0.43 1" specular="0.4"/>
    <material name="window" rgba="1 0.30 0.52 1" emission="1.0"/>
    <material name="coal" rgba="0.05 0.05 0.06 1"/>
    <material name="carrot" rgba="0.91 0.20 0.43 1"/>
    <material name="star" rgba="1 0.25 0.50 1" emission="1.0" specular="0.8"/>
    <material name="orn_red" rgba="0.91 0.20 0.43 1" specular="1" shininess="0.9" emission="0.45"/>
    <material name="orn_gold" rgba="0.97 0.97 0.97 1" specular="1" shininess="0.9" emission="0.45"/>
    <material name="orn_blue" rgba="0.91 0.20 0.43 1" specular="1" shininess="0.9" emission="0.45"/>
    <material name="orn_white" rgba="0.97 0.97 0.97 1" specular="1" shininess="0.9" emission="0.45"/>
    <material name="present_red" rgba="0.91 0.20 0.43 1" specular="0.4"/>
    <material name="present_green" rgba="0.05 0.05 0.05 1" specular="0.6" shininess="0.7"/>
    <material name="present_blue" rgba="0.93 0.93 0.93 1" specular="0.4"/>
    <material name="present_gold" rgba="0.20 0.20 0.21 1" specular="0.6"/>
    <material name="cane_red" rgba="0.91 0.20 0.43 1" specular="0.7" shininess="0.8"/>
    <material name="cane_white" rgba="0.97 0.97 0.97 1" specular="0.7" shininess="0.8"/>
    <material name="neon" rgba="1 1 1 1" emission="1.0"/>
    <material name="bulb_warm" rgba="1 1 1 1" emission="1.0"/>
    <material name="bulb_red" rgba="1 0.25 0.50 1" emission="1.0"/>
    <material name="bulb_green" rgba="1 1 1 1" emission="1.0"/>
    <material name="bulb_blue" rgba="1 0.25 0.50 1" emission="1.0"/>
    <mesh name="star" vertex="{star_vertices()}" scale="0.3 1.6 0.3"/>
{cone_meshes}
  </asset>

  <worldbody>
    <!-- Mondlicht (wirft Schatten), warmes Buehnenlicht, kuehles Gegenlicht -->
    <light name="moon" pos="4 -5 9" dir="-0.4 0.5 -1" directional="true" diffuse="0.40 0.40 0.44" specular="0.18 0.18 0.2"/>
    <light name="key" pos="3.2 1.8 3.4" dir="-1 -0.55 -0.9" cutoff="50" exponent="4" diffuse="1.0 0.97 0.95" specular="0.5 0.5 0.5" attenuation="0.5 0.06 0.012"/>
    <light name="rim" pos="-2.6 -2.6 3.0" dir="0.8 0.8 -0.8" cutoff="55" exponent="3" diffuse="1.0 0.22 0.48" specular="0.6 0.15 0.3" attenuation="0.6 0.08 0.02" castshadow="false"/>
    <geom name="floor" type="plane" size="0 0 0.05" pos="0 0 -0.04" material="snow"/>
    <camera name="front" pos="4.6 0 1.25" xyaxes="0 1 0 -0.06 0 1" fovy="48"/>
    <camera name="dance" mode="targetbody" target="pelvis" pos="3.3 -0.5 1.15" fovy="46"/>
    <camera name="wide"mode="targetbody" target="pelvis" pos="5.8 -1.4 2.6" fovy="52"/>
    <camera name="orbit" mode="targetbody" target="pelvis" pos="3.6 -2.4 1.5" fovy="45"/>
{body}
  </worldbody>
</mujoco>
"""


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print(f"geschrieben: {OUT}  ({len(geoms)} Deko-Elemente)")
