"""Local audio-file rating edits."""

import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import artwork_write
from .artwork import _require_local_artwork_origin
from .collection import collection_mcp, resolve_collection_audio
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


@router.put("/api/collection/tracks/{track_id}/rating")
async def set_rekordbox_track_rating(
    track_id: str, request: RatingUpdate, http_request: Request,
):
    _require_local_artwork_origin(http_request)
    source = await resolve_collection_audio(track_id)
    try:
        async with playlist_mutation_lock(str(source)):
            await asyncio.to_thread(artwork_write.set_audio_rating, source, request.rating)
    except artwork_write.ArtworkWriteError as error:
        raise HTTPException(400, str(error)) from None
    collection_mcp.track_paths[track_id] = source
    return {"rating": request.rating}
