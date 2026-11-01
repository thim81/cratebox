"""Image search, artwork overrides, and embedded artwork endpoint."""

import asyncio
import json
from pathlib import Path
import tempfile

from ddgs import DDGS
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from .artwork_data import embedded_artwork, is_http_url
from .config import ARTWORK_FILE, PLAN_DIRECTORY
from .playlists import find_playlist, parse_playlist, playlist_entries, playlist_files, read_plan_ids

router = APIRouter()

class ImageSearch(BaseModel):
    query: str

class ArtworkUpdate(BaseModel):
    playlist_id: str
    image_url: str
    track_id: str | None = None

@router.post("/api/images/search")
async def search_images(request: ImageSearch):
    query = request.query.strip()
    if not query or len(query) > 200:
        raise HTTPException(400, "Enter a search query up to 200 characters")
    try:
        results = await asyncio.to_thread(lambda: DDGS().images(query, max_results=24, safesearch="moderate"))
    except Exception:
        raise HTTPException(502, "Image search is temporarily unavailable. Try again later.") from None
    return [{
        "title": item.get("title", "")[:300],
        "image_url": item.get("image", ""),
        "thumbnail_url": item.get("thumbnail", "") if is_http_url(item.get("thumbnail", "")) else item.get("image", ""),
        "source_url": item.get("url", ""),
    } for item in results if is_http_url(item.get("image", "")) and is_http_url(item.get("url", ""))]

@router.put("/api/artwork")
def save_artwork(request: ArtworkUpdate):
    if request.playlist_id not in {path.stem for path in playlist_files()}:
        raise HTTPException(404, "Playlist not found")
    if len(request.image_url) > 2048 or not is_http_url(request.image_url):
        raise HTTPException(400, "Artwork must use an HTTP or HTTPS image URL")
    overrides = read_artwork_overrides()
    overrides.setdefault("playlists", {})
    overrides.setdefault("tracks", {})
    if request.track_id is None:
        overrides["playlists"][request.playlist_id] = request.image_url
    else:
        tracks = {track["id"] for track in parse_playlist(find_playlist(request.playlist_id))}
        if request.track_id not in tracks:
            raise HTTPException(404, "Track not found in playlist")
        overrides["tracks"].setdefault(request.playlist_id, {})[request.track_id] = request.image_url
    if PLAN_DIRECTORY.is_symlink():
        raise HTTPException(403, "Artwork settings cannot use a symlinked output directory")
    PLAN_DIRECTORY.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=PLAN_DIRECTORY, prefix=".cratedeck-artwork-", delete=False) as temporary:
        temporary.write(json.dumps(overrides, ensure_ascii=False, indent=2) + "\n")
        temporary_path = Path(temporary.name)
    temporary_path.replace(ARTWORK_FILE)
    return {"image_url": request.image_url}

@router.get("/api/playlists/{playlist_id}/tracks/{track_id}/artwork")
def get_track_artwork(playlist_id: str, track_id: str):
    path = find_playlist(playlist_id)
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        raise HTTPException(500, "Could not read playlist") from exc
    _, plan = read_plan_ids(path, lines)
    for _, _, audio, registered_id, _ in playlist_entries(path, lines, plan):
        if registered_id == track_id:
            artwork = embedded_artwork(audio)
            if artwork:
                data, media_type = artwork
                return Response(data, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"})
            break
    raise HTTPException(404, "Track artwork not found")

