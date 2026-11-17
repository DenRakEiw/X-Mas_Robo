"""Schreibt Pose-Daten und das Python-Ergebnis als Vergleichsdaten fuer web/test/retarget.test.mjs."""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).parent.parent
sys.path[:0] = [str(ROOT / "app"), str(ROOT / "sim")]
import pose, retarget

video = Path(sys.argv[1]); seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 6.0
track = pose.extract(video, seconds)
fps, qpos = retarget.retarget_track(track)
out = ROOT / "web" / "test" / "fixture.json"
out.parent.mkdir(exist_ok=True)
r = lambda a: [round(float(v), 5) for v in np.asarray(a).ravel()]
out.write_text(json.dumps(dict(fps=fps, world=[r(w) for w in track.world], vis=[r(v) for v in track.vis],
                               detected=[bool(d) for d in track.detected], qpos=[r(q) for q in qpos])), encoding="utf-8")
print("geschrieben", out, len(qpos), "Bilder")
