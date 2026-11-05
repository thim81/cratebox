"""Playlist and collection audio streaming endpoints."""

import subprocess
import sys

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .collection import collection_mcp
from .artwork_data import embedded_artwork
from .playlists import find_playlist, playlist_entries, read_plan_ids

router = APIRouter()


class RevealRequest(BaseModel):
    playlist_id: str | None = None
    track_id: str


@router.get("/api/collection/stream/{track_id}")
def collection_stream(track_id: str):
    audio_path = collection_mcp.track_paths.get(track_id)
    if audio_path is None or not audio_path.is_file():
        print(
            "Collection stream 404: "
            f"track_id={track_id} "
            f"reason={'path_not_cached' if audio_path is None else 'file_missing'} "
            f"mcp_state={collection_mcp.state} "
            f"cached_track_count={len(collection_mcp.track_paths)}",
            flush=True,
        )
        raise HTTPException(404, "Rekordbox track not found in the latest lookup.")
    return FileResponse(audio_path, headers={"Cache-Control": "no-store"})


@router.get("/api/collection/tracks/{track_id}/artwork")
def collection_track_artwork(track_id: str):
    audio_path = collection_mcp.track_paths.get(track_id)
    if audio_path is None or not audio_path.is_file():
        raise HTTPException(404, "Rekordbox track not found in the latest lookup.")
    artwork = embedded_artwork(audio_path)
    if artwork is None:
        raise HTTPException(404, "Track artwork not found.")
    data, media_type = artwork
    return Response(data, media_type=media_type, headers={"Cache-Control": "no-store"})


@router.post("/api/reveal")
def reveal_track(request: RevealRequest):
    if sys.platform != "darwin":
        raise HTTPException(501, "Finder reveal is available only on macOS.")

    audio_path = None
    if request.playlist_id:
        path = find_playlist(request.playlist_id)
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        _, plan = read_plan_ids(path, lines)
        audio_path = next(
            (audio for _, _, audio, track_id, _ in playlist_entries(path, lines, plan)
             if track_id == request.track_id),
            None,
        )
    else:
        audio_path = collection_mcp.track_paths.get(request.track_id)

    if audio_path is None or not audio_path.is_file():
        raise HTTPException(404, "Track file is unavailable.")
    try:
        subprocess.run(["open", "-R", str(audio_path)], check=True, timeout=5, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        raise HTTPException(500, "Could not reveal the track in Finder.") from None
    return {"revealed": True}

@router.get("/api/stream")
def stream(playlist_id: str, track_id: str):
    path = find_playlist(playlist_id)
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    _, plan = read_plan_ids(path, lines)
    for _, _, audio, registered_id, _ in playlist_entries(path, lines, plan):
        if registered_id == track_id:
            return FileResponse(audio)
    raise HTTPException(404, "Track not found in playlist")

