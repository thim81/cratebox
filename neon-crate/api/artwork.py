"""Image search, artwork overrides, and embedded artwork endpoint."""

import asyncio
from urllib.parse import quote, urlsplit

from ddgs import DDGS
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from .artwork_data import embedded_artwork, is_http_url, read_artwork_overrides, write_artwork_overrides
from . import artwork_write
from .playlists import find_playlist, parse_playlist, playlist_entries, playlist_files, read_plan_ids

router = APIRouter()

class ImageSearch(BaseModel):
    query: str

class ArtworkUpdate(BaseModel):
    playlist_id: str
    image_url: str
    track_id: str | None = None

class ArtworkEmbed(BaseModel):
    playlist_id: str
    track_id: str
    image_url: str

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
    write_artwork_overrides(overrides)
    return {"image_url": request.image_url}

@router.put("/api/artwork/embed")
def embed_artwork(request: ArtworkEmbed, http_request: Request):
    origin = http_request.headers.get("origin", "")
    try:
        parsed_origin = urlsplit(origin)
        origin_port = parsed_origin.port
    except ValueError:
        parsed_origin, origin_port = None, None
    if (
        parsed_origin is None
        or parsed_origin.scheme != "http"
        or parsed_origin.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed_origin.username
        or parsed_origin.password
        or origin_port != 8080
        or parsed_origin.path
        or parsed_origin.query
        or parsed_origin.fragment
    ):
        raise HTTPException(403, "Artwork embedding is allowed only from the local CrateDeck interface")
    if len(request.image_url) > 2048:
        raise HTTPException(400, "The selected image URL is too long")

    try:
        source = artwork_write.resolve_playlist_mp3(request.playlist_id, request.track_id)
        image_data, mime = artwork_write.download_cover_image(request.image_url)
        original_overrides = read_artwork_overrides()
        updated_overrides = {
            **original_overrides,
            "playlists": dict(original_overrides.get("playlists", {})),
            "tracks": {key: dict(value) for key, value in original_overrides.get("tracks", {}).items()},
        }
        track_overrides = updated_overrides["tracks"].get(request.playlist_id, {})
        had_override = request.track_id in track_overrides
        old_override = track_overrides.get(request.track_id)
        if had_override:
            track_overrides.pop(request.track_id)
            if track_overrides:
                updated_overrides["tracks"][request.playlist_id] = track_overrides
            else:
                updated_overrides["tracks"].pop(request.playlist_id, None)
            write_artwork_overrides(updated_overrides)
        try:
            backup = artwork_write.embed_cover_art(source, image_data, mime)
        except Exception:
            if had_override:
                original_overrides.setdefault("tracks", {}).setdefault(request.playlist_id, {})[
                    request.track_id
                ] = old_override
                write_artwork_overrides(original_overrides)
            raise
    except artwork_write.ArtworkWriteError as exc:
        raise HTTPException(400, str(exc)) from None

    artwork_url = (
        f"/api/playlists/{quote(request.playlist_id, safe='')}/tracks/"
        f"{quote(request.track_id, safe='')}/artwork?v={source.stat().st_mtime_ns}"
    )
    return {"backup_id": backup.name, "artwork_url": artwork_url}

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
                return Response(data, media_type=media_type, headers={"Cache-Control": "no-store"})
            break
    raise HTTPException(404, "Track artwork not found")

