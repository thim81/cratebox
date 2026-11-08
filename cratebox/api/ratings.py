"""Local audio-file rating edits."""

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import artwork_write
from .artwork import _require_local_artwork_origin
from .collection import collection_mcp
from .playlists import playlist_mutation_lock

router = APIRouter()


class RatingUpdate(BaseModel):
    rating: int = Field(strict=True, ge=0, le=5)


@router.put("/api/playlists/{playlist_id}/tracks/{track_id}/rating")
async def set_crate_track_rating(
    playlist_id: str, track_id: str, request: RatingUpdate, http_request: Request,
):
    _require_local_artwork_origin(http_request)
    try:
        source = artwork_write.resolve_playlist_mp3(playlist_id, track_id)
        async with playlist_mutation_lock(str(source)):
            await asyncio.to_thread(artwork_write.set_audio_rating, source, request.rating)
    except artwork_write.ArtworkWriteError as error:
        raise HTTPException(400, str(error)) from None
    return {"rating": request.rating}


@router.put("/api/rekordbox/playlists/{playlist_id}/tracks/{track_id}/rating")
async def set_rekordbox_track_rating(
    playlist_id: str, track_id: str, request: RatingUpdate, http_request: Request,
):
    _require_local_artwork_origin(http_request)
    from .rekordbox_playlists import call_tool, playlist_records

    if not any(str(item.get("id")) == playlist_id for item in await playlist_records()):
        raise HTTPException(404, "Rekordbox playlist not found.")
    tracks = await call_tool("get_playlist_tracks", {"playlist_id": playlist_id})
    if not isinstance(tracks, list) or not any(
        isinstance(item, dict) and str(item.get("id")) == track_id for item in tracks
    ):
        raise HTTPException(404, "Track not found in Rekordbox playlist.")
    locations = await call_tool("get_collection_tracks", {"track_ids": [track_id]})
    if (
        not isinstance(locations, list) or len(locations) != 1
        or not isinstance(locations[0], dict)
        or str(locations[0].get("id")) != track_id
        or not isinstance(locations[0].get("file_path"), str)
        or any(character in locations[0]["file_path"] for character in "\r\n\x00\x85\u2028\u2029")
        or not Path(locations[0]["file_path"]).is_absolute()
    ):
        raise HTTPException(409, "The Rekordbox track no longer resolves to one local audio file.")

    source = Path(locations[0]["file_path"])
    try:
        async with playlist_mutation_lock(str(source)):
            await asyncio.to_thread(artwork_write.set_audio_rating, source, request.rating)
    except artwork_write.ArtworkWriteError as error:
        raise HTTPException(400, str(error)) from None
    collection_mcp.track_paths[track_id] = source
    return {"rating": request.rating}
