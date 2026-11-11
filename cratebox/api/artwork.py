"""Image search, artwork overrides, and embedded artwork endpoint."""

import asyncio
import logging
from urllib.parse import quote, urlsplit
from uuid import uuid4

from ddgs import DDGS
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from .artwork_data import embedded_artwork, is_http_url, read_artwork_overrides, write_artwork_overrides
from . import artwork_write
from . import google_image_search
from . import music_artwork
from .collection import collection_mcp, resolve_collection_audio
from .playlists import find_playlist, parse_playlist, playlist_entries, playlist_files, playlist_mutation_lock, read_plan_ids

router = APIRouter()
logger = logging.getLogger(__name__)

class ImageSearch(BaseModel):
    query: str
    artist: str = ""
    album: str = ""
    track: str = ""
    cover_art: bool = True
    musicbrainz: bool = False
    google_images: bool = True
    duckduckgo: bool = False
    spotify: bool = False
    soundcloud: bool = False

class ArtworkUpdate(BaseModel):
    playlist_id: str
    image_url: str
    track_id: str | None = None

class ArtworkEmbed(BaseModel):
    playlist_id: str
    track_id: str
    image_url: str


class RekordboxArtworkEmbed(BaseModel):
    image_url: str

@router.post("/api/images/search")
async def search_images(request: ImageSearch):
    query = request.query.strip()
    if not query or len(query) > 200:
        raise HTTPException(400, "Enter a search query up to 200 characters")
    try:
        results = await asyncio.to_thread(
            search_image_results,
            query,
            artist=request.artist[:200],
            album=request.album[:200],
            track=request.track[:200],
            cover_art=request.cover_art,
            musicbrainz=request.musicbrainz,
            google_images=request.google_images,
            duckduckgo=request.duckduckgo,
            spotify=request.spotify,
            soundcloud=request.soundcloud,
        )
    except google_image_search.GoogleVerificationRequired as exc:
        raise HTTPException(503, str(exc)) from None
    except Exception:
        raise HTTPException(502, "Image search is temporarily unavailable. Try again later.") from None
    return results


def search_image_results(
    query: str, *, artist: str = "", album: str = "", track: str = "", cover_art: bool = True,
    musicbrainz: bool = False, google_images: bool = True, duckduckgo: bool = False,
    spotify: bool = False, soundcloud: bool = False,
):
    catalogue_results = []
    seen_urls = set()
    if musicbrainz:
        for item in music_artwork.search_music_artwork(query, artist=artist, album=album, track=track):
            if not isinstance(item, dict):
                continue
            image_url = item.get("image_url", "")
            if not is_http_url(image_url) or image_url in seen_urls:
                continue
            catalogue_results.append(item)
            seen_urls.add(image_url)
            if len(catalogue_results) == 24:
                break
    if cover_art:
        query = f"{query[:160]} track single cover artwork"
    if spotify:
        query += " Spotify"
    if soundcloud:
        query += " SoundCloud"
    combined = list(catalogue_results)
    verification_error = None
    google_results = []
    if google_images:
        try:
            google_results = google_image_search.search_google_images(query, limit=24)
        except google_image_search.GoogleVerificationRequired as exc:
            verification_error = exc
            logger.warning("Google Images requires human verification: %s", exc)
        except Exception as exc:
            logger.warning("Google Images search failed: %s", exc)
        else:
            logger.info("Google Images returned %d results", len(google_results))
    for item in google_results:
        image_url = item.get("image_url", "")
        if image_url not in seen_urls:
            combined.append(item)
            seen_urls.add(image_url)
            if len(combined) == 24:
                return combined

    if not duckduckgo:
        if verification_error and not combined:
            raise verification_error
        return combined
    try:
        ddg_results = DDGS().images(query, max_results=24, safesearch="moderate")
    except Exception:
        if combined:
            return combined
        if verification_error:
            raise verification_error
        raise
    for item in ddg_results:
        if not isinstance(item, dict):
            continue
        image_url = item.get("image", "")
        source_url = item.get("url", "")
        if not is_http_url(image_url) or not is_http_url(source_url) or image_url in seen_urls:
            continue
        thumbnail_url = item.get("thumbnail", "")
        combined.append({
            "title": item.get("title", "")[:300] if isinstance(item.get("title"), str) else "",
            "image_url": image_url,
            "thumbnail_url": thumbnail_url if is_http_url(thumbnail_url) else image_url,
            "source_url": source_url,
            "source": "DuckDuckGo",
        })
        seen_urls.add(image_url)
        if len(combined) == 24:
            break
    if not combined and verification_error:
        raise verification_error
    return combined

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
    _require_local_artwork_origin(http_request)
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
            artwork_write.embed_cover_art(source, image_data, mime)
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
        f"{quote(request.track_id, safe='')}/artwork?v={uuid4().hex}"
    )
    return {"backup_id": None, "artwork_url": artwork_url}


def _require_local_artwork_origin(http_request: Request):
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
        or origin_port != 4444
        or parsed_origin.path
        or parsed_origin.query
        or parsed_origin.fragment
    ):
        raise HTTPException(403, "Artwork embedding is allowed only from the local CrateBox interface")


@router.put("/api/collection/tracks/{track_id}/artwork/embed")
async def embed_rekordbox_artwork(
    track_id: str, request: RekordboxArtworkEmbed, http_request: Request,
):
    _require_local_artwork_origin(http_request)
    if len(request.image_url) > 2048:
        raise HTTPException(400, "The selected image URL is too long")

    source = await resolve_collection_audio(track_id)
    try:
        artwork_write._validate_source(source)
        image_data, mime = await asyncio.to_thread(artwork_write.download_cover_image, request.image_url)
        async with playlist_mutation_lock(str(source)):
            await asyncio.to_thread(artwork_write.embed_cover_art, source, image_data, mime)
    except artwork_write.ArtworkWriteError as exc:
        raise HTTPException(400, str(exc)) from None

    collection_mcp.track_paths[track_id] = source
    return {
        "backup_id": None,
        "artwork_url": f"/api/collection/tracks/{quote(track_id, safe='')}/artwork?v={uuid4().hex}",
    }

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

