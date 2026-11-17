"""Lokale Oberflaeche: Link einfuegen, Roboter tanzen sehen.

    .venv/Scripts/python server.py        ->  http://localhost:8765
"""
from __future__ import annotations

import json
import queue
import re
import subprocess
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path

ROOT = Path(__file__).parent
sys.path[:0] = [str(ROOT / "app"), str(ROOT / "sim")]

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import pipeline

PORT = 8765
app = FastAPI(title="Dance Transfer")
jobs: dict[str, dict] = {}
todo: "queue.Queue[str]" = queue.Queue()


def worker() -> None:
    """Ein Job nach dem anderen: Pose-Erkennung und Rendern teilen sich Rechner und Grafikkontext."""
    while True:
        jid = todo.get()
        job = jobs[jid]
        job["status"] = "running"

        def on_progress(stage: str, frac: float) -> None:
            job["stage"], job["progress"] = stage, round(float(frac), 3)

        try:
            job["result"] = pipeline.run(job["source"], None, job["max_seconds"], on_progress=on_progress)
            job["status"] = "done"
        except Exception as e:  # Fehlertext geht an die Oberflaeche
            traceback.print_exc()
            job["status"], job["error"] = "error", f"{type(e).__name__}: {e}"[:400]


threading.Thread(target=worker, daemon=True).start()


def find(name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name) or not (pipeline.MOTIONS / f"{name}.npz").exists():
        raise HTTPException(404, "unbekannter Tanz")
    return pipeline.MOTIONS / f"{name}.npz"


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "ui" / "index.html", headers={"Cache-Control": "no-store"})


@app.post("/api/jobs")
async def create_job(req: Request) -> dict:
    body = await req.json()
    source = str(body.get("source", "")).strip()
    if not source:
        raise HTTPException(400, "Link oder Datei fehlt")
    if not re.match(r"^https?://", source):
        # lokale Dateien nur aus dem Upload-Ordner
        source = str(pipeline.VIDEOS / Path(source).name)
        if not Path(source).exists():
            raise HTTPException(400, "Das ist kein Link")
    ms = body.get("max_seconds")
    jid = uuid.uuid4().hex[:10]
    jobs[jid] = dict(id=jid, source=source, max_seconds=float(ms) if ms else None, status="queued",
                     stage="fetch", progress=0.0, result=None, error=None, started=time.time())
    todo.put(jid)
    return jobs[jid]


@app.get("/api/jobs/{jid}")
def get_job(jid: str) -> dict:
    if jid not in jobs:
        raise HTTPException(404, "unbekannter Job")
    return jobs[jid]


@app.put("/api/upload")
async def upload(req: Request, name: str) -> dict:
    """Videodatei als Rohdaten im Body."""
    ext = Path(name).suffix.lower()
    if ext not in (".mp4", ".mov", ".webm", ".mkv", ".m4v"):
        raise HTTPException(400, "nur mp4, mov, webm, mkv")
    pipeline.VIDEOS.mkdir(exist_ok=True)
    dest = pipeline.VIDEOS / f"upload_{pipeline.safe_name(Path(name).stem)}{ext}"
    with open(dest, "wb") as f:
        async for chunk in req.stream():
            f.write(chunk)
    return {"file": dest.name}


@app.get("/api/dances")
def dances() -> list[dict]:
    items = []
    for npz in pipeline.MOTIONS.glob("*.npz"):
        meta_file, name = npz.with_suffix(".json"), npz.stem
        mp4, jpg = pipeline.OUT / f"{name}.mp4", pipeline.OUT / f"{name}.jpg"
        if not mp4.exists():
            continue
        meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else dict(name=name, title=name)
        if not jpg.exists():
            pipeline.poster(mp4, jpg)
        meta.update(name=name, video=f"/media/{name}.mp4", poster=f"/media/{name}.jpg", mtime=npz.stat().st_mtime)
        items.append(meta)
    return sorted(items, key=lambda m: -m["mtime"])


@app.post("/api/dances/{name}/open3d")
def open3d(name: str) -> dict:
    """Oeffnet das interaktive 3D-Fenster auf diesem Rechner."""
    npz = find(name)
    subprocess.Popen([sys.executable, str(ROOT / "sim" / "play.py"), str(npz)], cwd=str(ROOT))
    return {"ok": True}


@app.delete("/api/dances/{name}")
def delete(name: str) -> dict:
    npz = find(name)
    for f in (npz, npz.with_suffix(".json"), pipeline.OUT / f"{name}.mp4", pipeline.OUT / f"{name}.jpg"):
        f.unlink(missing_ok=True)
    return {"ok": True}


pipeline.OUT.mkdir(exist_ok=True)
pipeline.MOTIONS.mkdir(exist_ok=True)
app.mount("/media", StaticFiles(directory=pipeline.OUT), name="media")

if __name__ == "__main__":
    print(f"Oberflaeche: http://localhost:{PORT}")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
