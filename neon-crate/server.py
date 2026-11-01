"""Local API for the CrateDeck playlist browser."""

from datetime import date
from pathlib import Path
import hashlib
from urllib.parse import quote
import os
import tempfile

import mutagen
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

DEFAULT_PLAYLIST_DIR = Path(__file__).resolve().parents[1] / "playlists"
PLAYLIST_DIR = Path(os.environ.get("PLAYLIST_DIR", str(DEFAULT_PLAYLIST_DIR))).expanduser().resolve()
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


def playlist_entries(path: Path, lines: list[str]):
    occurrences = {}
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
        audio_key = str(audio)
        occurrence = occurrences.get(audio_key, 0)
        occurrences[audio_key] = occurrence + 1
        digest = hashlib.blake2b(audio_key.encode(), digest_size=8).hexdigest()
        yield line_number, audio, f"{path.stem}-{digest}-{occurrence}"


def parse_playlist(path: Path):
    tracks = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        raise HTTPException(500, f"Could not read playlist {path.name}") from exc

    for _, audio, track_id in playlist_entries(path, lines):
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


@app.delete("/api/playlists/{playlist_id}/tracks")
def delete_tracks(playlist_id: str, track_ids: list[str] = Body(..., embed=True)):
    if DEFAULT_PLAYLIST_DIR.is_symlink() or PLAYLIST_DIR != DEFAULT_PLAYLIST_DIR:
        raise HTTPException(403, "Playlist edits are limited to the app's playlists folder")
    if not track_ids or len(track_ids) > 1000 or len(set(track_ids)) != len(track_ids):
        raise HTTPException(400, "Select between 1 and 1000 unique tracks")

    path = find_playlist(playlist_id)
    try:
        with path.open(encoding="utf-8-sig", newline="") as playlist:
            lines = playlist.readlines()
    except (OSError, UnicodeError) as exc:
        raise HTTPException(500, "Could not read playlist") from exc

    entries = {track_id: index for index, _, track_id in playlist_entries(path, lines)}
    remove_indices = set()
    for track_id in track_ids:
        if track_id not in entries:
            raise HTTPException(404, "Track not found in playlist")
        index = entries[track_id]
        remove_indices.add(index)
        if index and lines[index - 1].lstrip().startswith("#EXTINF:"):
            remove_indices.add(index - 1)

    updated_lines = [line for index, line in enumerate(lines) if index not in remove_indices]
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary.writelines(updated_lines)
        temporary_path.chmod(path.stat().st_mode)
        os.replace(temporary_path, path)
    except OSError as exc:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
        raise HTTPException(500, "Could not update playlist") from exc
    return {"removed": len(track_ids)}


@app.get("/api/stream")
def stream(playlist_id: str, track_id: str):
    path = find_playlist(playlist_id)
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    for _, audio, registered_id in playlist_entries(path, lines):
        if registered_id == track_id:
            return FileResponse(audio)
    raise HTTPException(404, "Track not found in playlist")
