"""TikTok-Link (oder Videodatei) rein, tanzender G1 in der Weihnachts-Szene raus.

    .venv/Scripts/python dance.py "https://www.tiktok.com/@name/video/123..."
    .venv/Scripts/python dance.py pfad/zum/video.mp4 --no-window

Ergebnis:
    motions/<name>.npz   Bewegung fuer sim/play.py
    out/<name>.mp4       Vergleichsvideo Original | Roboter, mit Ton
Danach oeffnet sich das 3D-Fenster mit dem Tanz in Schleife (ausser mit --no-window).
Die Oberflaeche dazu startet mit:  .venv/Scripts/python server.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path[:0] = [str(ROOT / "app"), str(ROOT / "sim")]

LABELS = {"fetch": "Video holen", "pose": "Pose erkennen", "retarget": "Auf G1 uebertragen", "render": "Video rendern"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="Link (TikTok, YouTube, ...) oder lokale Videodatei")
    ap.add_argument("--name", help="Name der Ausgabedateien (Standard: Name des Videos)")
    ap.add_argument("--max-seconds", type=float, help="nur den Anfang des Videos verarbeiten")
    ap.add_argument("--camera", default="dance", help="Kamera im Vergleichsvideo: dance, front, wide, orbit")
    ap.add_argument("--no-video", action="store_true", help="kein Vergleichsvideo rendern")
    ap.add_argument("--no-window", action="store_true", help="3D-Fenster am Ende nicht oeffnen")
    args = ap.parse_args()

    import pipeline

    last = [""]

    def show(stage: str, frac: float) -> None:
        if stage != last[0]:
            if last[0]:
                print()
            last[0] = stage
        print(f"\r{LABELS[stage]}: {100 * frac:3.0f}%", end="", flush=True)

    meta = pipeline.run(args.source, args.name, args.max_seconds, args.camera, not args.no_video, show)
    print(f"\nFertig: {meta['seconds']} s Video in {meta['took']} s, Person in {100 * meta['detected']:.0f}% der Bilder erkannt")
    print(f"  motions/{meta['name']}.npz" + (f"\n  out/{meta['video']}" if meta["video"] else ""))

    if not args.no_window:
        import motion
        import mujoco
        import play
        fps, qpos = motion.load(ROOT / "motions" / f"{meta['name']}.npz")
        model = mujoco.MjModel.from_xml_path(str(play.SCENE))
        play.run_window(model, mujoco.MjData(model), fps, qpos, None, loop=True)


if __name__ == "__main__":
    main()
