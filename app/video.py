"""Video holen: Link (TikTok, YouTube, ...) per yt-dlp oder lokale Datei."""
from __future__ import annotations

import re
from pathlib import Path


def fetch(source: str, out_dir: Path) -> tuple[Path, str | None]:
    """Gibt (Pfad zur lokalen Videodatei, Titel) zurueck. Lokale Dateien werden direkt benutzt."""
    p = Path(source)
    if p.exists():
        return p.resolve(), None
    if not re.match(r"^https?://", source):
        raise FileNotFoundError(f"Weder Datei noch Link: {source}")

    import yt_dlp

    out_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "outtmpl": str(out_dir / "%(extractor)s_%(id)s.%(ext)s"),
        # hoechstens 1080 Pixel Kantenlaenge reicht fuer die Pose-Erkennung
        "format": "bv*[height<=1920][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    try:
        import imageio_ffmpeg
        opts["ffmpeg_location"] = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(source, download=True)
        path = Path(ydl.prepare_filename(info))
    if not path.exists():
        path = path.with_suffix(".mp4")
    return path.resolve(), info.get("title")
