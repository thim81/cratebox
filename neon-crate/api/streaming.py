"""Playlist and collection audio streaming endpoints."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .collection import collection_mcp
from .playlists import find_playlist, playlist_entries, read_plan_ids

router = APIRouter()

@router.get("/api/collection/stream/{track_id}")
def collection_stream(track_id: str):
    audio_path = collection_mcp.track_paths.get(track_id)
    if audio_path is None or not audio_path.is_file():
        raise HTTPException(404, "Rekordbox track not found in the latest lookup.")
    return FileResponse(audio_path, headers={"Cache-Control": "no-store"})

@router.get("/api/stream")
def stream(playlist_id: str, track_id: str):
    path = find_playlist(playlist_id)
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    _, plan = read_plan_ids(path, lines)
    for _, _, audio, registered_id, _ in playlist_entries(path, lines, plan):
        if registered_id == track_id:
            return FileResponse(audio)
    raise HTTPException(404, "Track not found in playlist")

