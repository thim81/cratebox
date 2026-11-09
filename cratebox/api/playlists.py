"""Playlist parsing, operations, and endpoints."""

from datetime import date
from pathlib import Path
from urllib.parse import quote

import mutagen
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from .artwork_data import embedded_artwork, read_artwork_overrides
from .collection import collection_mcp
from .config import (
    DEFAULT_PLAYLIST_DIR,
    CRATE_DIRECTORY,
    PLAYLIST_DIR,
)
from core.revision import PlaylistRevision
from core.mutations import playlist_mutation_lock
from core.crates import (
    ApplicationError,
    atomic_write as core_atomic_write,
    crate_files as core_crate_files,
    create_crate as core_create_crate,
    find_crate as core_find_crate,
    playlist_entries as core_playlist_entries,
    parse_crate_tracks as core_parse_crate_tracks,
    read_plan_ids as core_read_plan_ids,
    remove_crate_tracks as core_remove_crate_tracks,
    reorder_crate_tracks as core_reorder_crate_tracks,
    replace_crate_track as core_replace_crate_track,
)

router = APIRouter()
playlist_revision = PlaylistRevision(PLAYLIST_DIR, CRATE_DIRECTORY)

class PlaylistSwap(BaseModel):
    source_track_id: str
    replacement_track_id: str

class PlaylistReorder(BaseModel):
    source_track_id: str | None = None
    source_track_ids: list[str] | None = None
    target_track_id: str
    before: bool

class PlaylistCreate(BaseModel):
    name: str

def playlist_files():
    return core_crate_files(PLAYLIST_DIR, CRATE_DIRECTORY)


def playlist_entries(path: Path, lines: list[str], plan, *, include_missing: bool = False):
    return core_playlist_entries(path, lines, plan, include_missing=include_missing)


def read_plan_ids(path: Path, lines: list[str]):
    return _call_core(core_read_plan_ids, path, lines, CRATE_DIRECTORY)


atomic_write = core_atomic_write


def _call_core(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except ApplicationError as error:
        raise HTTPException(error.status_code, error.detail) from None

def parse_playlist(path: Path):
    records = _call_core(
        core_parse_crate_tracks, path, CRATE_DIRECTORY, media_reader=mutagen.File,
    )
    tracks = []
    for record in records:
        audio = record.pop("_audio_path")
        track_id = record["id"]
        record.update({
            "url": f"/api/stream?playlist_id={quote(path.stem)}&track_id={quote(track_id)}",
            "artwork_url": f"/api/playlists/{quote(path.stem)}/tracks/{quote(track_id)}/artwork",
            "has_artwork": embedded_artwork(audio) is not None,
        })
        tracks.append(record)
    return tracks

def playlist_summary(path: Path, tracks):
    created = date.fromtimestamp(path.stat().st_ctime).isoformat()
    overrides = read_artwork_overrides()
    return {
        "id": path.stem,
        "name": path.stem,
        "trackCount": len(tracks),
        "duration": sum(track["duration"] for track in tracks),
        "created": created,
        "artwork_url": overrides.get("playlists", {}).get(path.stem),
    }

def find_playlist(playlist_id: str):
    return _call_core(core_find_crate, playlist_id, PLAYLIST_DIR, CRATE_DIRECTORY)

@router.get("/api/playlists")
def list_playlists():
    return [playlist_summary(path, parse_playlist(path)) for path in playlist_files()]


@router.get("/api/playlists/revision")
def get_playlist_revision():
    return {"revision": playlist_revision.value()}

@router.post("/api/playlists")
async def create_playlist(request: PlaylistCreate):
    async with playlist_mutation_lock(request.name.strip()):
        return _create_playlist(request)


def _create_playlist(request: PlaylistCreate):
    path = _call_core(
        core_create_crate, request.name, PLAYLIST_DIR, CRATE_DIRECTORY, DEFAULT_PLAYLIST_DIR,
    )
    return playlist_summary(path, [])

@router.get("/api/playlists/{playlist_id}")
def get_playlist(playlist_id: str):
    path = find_playlist(playlist_id)
    tracks = parse_playlist(path)
    overrides = read_artwork_overrides().get("tracks", {}).get(path.stem, {})
    for track in tracks:
        if track["id"] in overrides:
            track["fallback_artwork_url"] = track["artwork_url"]
            track["artwork_url"] = overrides[track["id"]]
            track["has_artwork"] = True
    return {**playlist_summary(path, tracks), "tracks": tracks}

@router.delete("/api/playlists/{playlist_id}/tracks")
async def delete_tracks(playlist_id: str, track_ids: list[str] = Body(..., embed=True)):
    async with playlist_mutation_lock(playlist_id):
        return _delete_tracks(playlist_id, track_ids)


def _delete_tracks(playlist_id: str, track_ids: list[str]):
    return _call_core(
        core_remove_crate_tracks, playlist_id, track_ids,
        PLAYLIST_DIR, CRATE_DIRECTORY, DEFAULT_PLAYLIST_DIR,
    )

@router.post("/api/playlists/{playlist_id}/tracks/swap")
async def swap_track(playlist_id: str, request: PlaylistSwap):
    async with playlist_mutation_lock(playlist_id):
        return _swap_track(playlist_id, request)


def _swap_track(playlist_id: str, request: PlaylistSwap):
    replacement_audio = collection_mcp.track_paths.get(request.replacement_track_id)
    return _call_core(
        core_replace_crate_track, playlist_id,
        request.source_track_id, request.replacement_track_id, replacement_audio,
        PLAYLIST_DIR, CRATE_DIRECTORY, DEFAULT_PLAYLIST_DIR,
    )


@router.post("/api/playlists/{playlist_id}/tracks/reorder")
async def reorder_track(playlist_id: str, request: PlaylistReorder):
    async with playlist_mutation_lock(playlist_id):
        return _reorder_track(playlist_id, request)


def _reorder_track(playlist_id: str, request: PlaylistReorder):
    source_track_ids = request.source_track_ids
    if source_track_ids is None:
        source_track_ids = [request.source_track_id] if request.source_track_id else []
    return _call_core(
        core_reorder_crate_tracks, playlist_id, source_track_ids,
        request.target_track_id, request.before,
        PLAYLIST_DIR, CRATE_DIRECTORY, DEFAULT_PLAYLIST_DIR,
    )

