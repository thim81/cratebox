"""Local, read-only API for the CrateDeck playlist browser."""

from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote
import os

import mutagen
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

PLAYLIST_DIR = Path(os.environ.get("PLAYLIST_DIR", "~/Music/Playlists")).expanduser().resolve()
app = FastAPI(title="CrateDeck playlist API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def playlist_files():
    return sorted(
        (p for p in PLAYLIST_DIR.glob("*.m3u*") if p.is_file() and p.suffix.lower() in {".m3u", ".m3u8"}),
        key=lambda p: (p.stem.casefold(), p.name.casefold()),
    )


def parse_playlist(path: Path):
    tracks = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        raise HTTPException(500, f"Could not read playlist {path.name}") from exc

    for line_number, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        audio = Path(line).expanduser()
        if not audio.is_absolute():
            audio = path.parent / audio
        audio = audio.resolve()
        if not audio.is_file():
            continue

        try:
            media = mutagen.File(audio, easy=True)
        except (OSError, ValueError):
            media = None
        tags = media or {}
        info = getattr(media, "info", None)

        def tag(key, default=""):
            values = tags.get(key, [])
            return str(values[0]) if values else default

        try:
            bpm = int(float(tag("bpm", "0") or 0))
        except (TypeError, ValueError):
            bpm = 0
        bitrate = getattr(info, "bitrate", 0) or 0
        track_id = f"{path.stem}-{line_number}"
        tracks.append({
            "id": track_id,
            "title": tag("title", audio.stem),
            "artist": tag("artist"),
            "album": tag("album"),
            "duration": round(getattr(info, "length", 0) or 0),
            "rating": 0,
            "bpm": bpm,
            "key": tag("initialkey"),
            "quality": f"{audio.suffix[1:].upper()} {bitrate // 1000}kbps".strip(),
            "url": f"/api/stream?playlist_id={quote(path.stem)}&track_id={quote(track_id)}",
        })
    return tracks


def playlist_summary(path: Path, tracks):
    created = date.fromtimestamp(path.stat().st_ctime).isoformat()
    return {
        "id": path.stem,
        "name": path.stem,
        "trackCount": len(tracks),
        "duration": sum(track["duration"] for track in tracks),
        "created": created,
    }


def find_playlist(playlist_id: str):
    matches = [p for p in playlist_files() if p.stem == playlist_id]
    if not matches:
        raise HTTPException(404, "Playlist not found")
    return matches[0]


@app.get("/api/playlists")
def list_playlists():
    return [playlist_summary(path, parse_playlist(path)) for path in playlist_files()]


@app.get("/api/playlists/{playlist_id}")
def get_playlist(playlist_id: str):
    path = find_playlist(playlist_id)
    tracks = parse_playlist(path)
    return {**playlist_summary(path, tracks), "tracks": tracks}


@app.get("/api/stream")
def stream(playlist_id: str, track_id: str):
    path = find_playlist(playlist_id)
    for track in parse_playlist(path):
        if track["id"] == track_id:
            # Resolve the registered playlist entry again; request paths are never accepted.
            for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines()):
                if f"{path.stem}-{line_number}" == track_id and line.strip() and not line.lstrip().startswith("#"):
                    audio = Path(line.strip()).expanduser()
                    if not audio.is_absolute():
                        audio = path.parent / audio
                    audio = audio.resolve()
                    if audio.is_file():
                        return FileResponse(audio)
            break
    raise HTTPException(404, "Track not found in playlist")
