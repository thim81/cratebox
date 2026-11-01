"""Read-only Rekordbox playlist browsing and local copy operations."""

import json
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .collection import collection_mcp
from .config import DEFAULT_PLAYLIST_DIR, PLAYLIST_DIR
from .playlists import playlist_entries, playlist_files, read_plan_ids

router = APIRouter()


class CopyPlaylistRequest(BaseModel):
    name: str
    update_existing: bool = False


class InsertSeparatorRequest(BaseModel):
    type: Literal["generic", "90s", "R&B", "Ambi", "Salsa", "Party", "Dance"]
    before_track_id: str
    confirm_update: bool = False


class AppendTrackRequest(BaseModel):
    track_id: str
    confirm_update: bool = False


def result_value(result):
    structured = result.structured_content
    value = structured.get("result") if isinstance(structured, dict) and "result" in structured else structured
    if value is None:
        value = result.data
    if value is None and result.content:
        value = json.loads(result.content[0].text)
    return value


async def call_tool(name: str, arguments: dict | None = None):
    client = await collection_mcp.connect()
    try:
        result = await client.call_tool(name, arguments or {})
    except Exception:
        raise HTTPException(502, "Rekordbox playlist request failed.") from None
    if result.is_error:
        message = next((item.text for item in result.content if hasattr(item, "text")), "")
        if "already exists" in message.lower():
            raise HTTPException(409, "A CrateDeck playlist with this name already exists.")
        if name == "export_playlist":
            raise HTTPException(400, message or "Could not export the Rekordbox playlist.")
        raise HTTPException(502, "Rekordbox playlist request failed.")
    try:
        return result_value(result)
    except (IndexError, TypeError, json.JSONDecodeError):
        raise HTTPException(502, "Unexpected response from Rekordbox.") from None


async def playlist_records():
    records = await call_tool("get_playlists")
    if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
        raise HTTPException(502, "Unexpected Rekordbox playlist list.")
    return records


def local_playlist_with_plan(playlist_id: str):
    if DEFAULT_PLAYLIST_DIR.is_symlink() or PLAYLIST_DIR != DEFAULT_PLAYLIST_DIR:
        raise HTTPException(403, "Playlist edits are limited to the app's playlists folder")
    matches = [item for item in playlist_files() if item.stem == playlist_id]
    if len(matches) != 1 or matches[0].suffix.lower() != ".m3u8":
        raise HTTPException(409, "Playlist edits require one unambiguous .m3u8 playlist")

    path = matches[0]
    try:
        with path.open(encoding="utf-8-sig", newline="") as playlist:
            lines = playlist.readlines()
    except (OSError, UnicodeError) as exc:
        raise HTTPException(500, "Could not read playlist") from exc

    _, plan = read_plan_ids(path, lines)
    if plan is None or plan[1] is None:
        raise HTTPException(409, "A valid track-ID and file-path plan is required to edit this playlist")
    return path, plan, lines


@router.get("/api/rekordbox/playlists")
async def get_rekordbox_playlists():
    return [
        {
            "id": str(record.get("id") or ""),
            "name": str(record.get("name") or ""),
            "parent_id": record.get("parent_id"),
            "is_folder": bool(record.get("is_folder")),
            "is_smart_playlist": bool(record.get("is_smart_playlist")),
            "track_count": int(record.get("track_count") or 0),
            "created_date": record.get("created_date"),
            "sequence": int(record.get("sequence") or 0),
        }
        for record in await playlist_records()
        if record.get("id") is not None
    ]


@router.get("/api/rekordbox/playlists/{playlist_id}/tracks")
async def get_rekordbox_playlist_tracks(playlist_id: str):
    records = await call_tool("get_playlist_tracks", {"playlist_id": playlist_id})
    if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
        raise HTTPException(502, "Unexpected Rekordbox playlist tracks.")
    occurrences: dict[str, int] = {}
    tracks = []
    for record in records:
        if record.get("id") is None:
            continue
        rekordbox_id = str(record["id"])
        occurrence = occurrences.get(rekordbox_id, 0)
        occurrences[rekordbox_id] = occurrence + 1
        tracks.append({
            "id": f"{rekordbox_id}-{occurrence + 1}",
            "rekordbox_id": rekordbox_id,
            "title": str(record.get("title") or ""),
            "artist": str(record.get("artist") or ""),
            "album": str(record.get("album") or ""),
            "duration": int(record.get("length") or 0),
            "rating": int(record.get("rating") or 0),
            "bpm": float(record.get("bpm") or 0),
            "key": str(record.get("key") or ""),
            "quality": "Rekordbox library",
            "url": "",
        })
    return tracks


@router.post("/api/rekordbox/playlists/{playlist_id}/copy")
async def copy_rekordbox_playlist(playlist_id: str, request: CopyPlaylistRequest):
    name = request.name.strip()
    if not name:
        raise HTTPException(400, "Enter a name for the CrateDeck copy.")

    source = next(
        (record for record in await playlist_records() if str(record.get("id")) == playlist_id),
        None,
    )
    if source is None:
        raise HTTPException(404, "Rekordbox playlist not found.")
    if source.get("is_folder"):
        raise HTTPException(400, "Folders cannot be copied as playlists.")

    tracks = await call_tool("get_playlist_tracks", {"playlist_id": playlist_id})
    if not isinstance(tracks, list):
        raise HTTPException(502, "Unexpected Rekordbox playlist tracks.")
    track_ids = [str(track.get("id") or "") for track in tracks if isinstance(track, dict)]
    if not track_ids or len(track_ids) != len(tracks) or any(not track_id for track_id in track_ids):
        raise HTTPException(400, "This Rekordbox playlist has no tracks to copy.")

    exported = await call_tool(
        "export_playlist",
        {"name": name, "track_ids": track_ids, "update_existing": request.update_existing},
    )
    if not isinstance(exported, dict):
        raise HTTPException(502, "Unexpected playlist export response.")
    return {
        "name": str(exported.get("name") or name),
        "track_count": int(exported.get("track_count") or len(track_ids)),
        "updated_existing": bool(exported.get("updated_existing")),
    }


@router.post("/api/playlists/{playlist_id}/separators")
async def insert_playlist_separator(playlist_id: str, request: InsertSeparatorRequest):
    if not request.confirm_update:
        raise HTTPException(400, "Confirm updating this playlist before inserting a separator.")
    path, plan, lines = local_playlist_with_plan(playlist_id)
    entries = list(playlist_entries(path, lines, plan))
    target = next((entry for entry in entries if entry[3] == request.before_track_id), None)
    if target is None:
        raise HTTPException(404, "Selected track not found in playlist")

    exported = await call_tool(
        "export_playlist",
        {
            "name": path.stem,
            "track_ids": plan[0],
            "update_existing": True,
            "separators": [{"type": request.type, "before_track": target[1] + 1}],
        },
    )
    if not isinstance(exported, dict):
        raise HTTPException(502, "Unexpected playlist export response.")
    return {
        "name": str(exported.get("name") or path.stem),
        "track_count": int(exported.get("track_count") or len(plan[0])),
        "separator_count": int(exported.get("separator_count") or 0),
        "updated_existing": bool(exported.get("updated_existing")),
    }


@router.post("/api/playlists/{playlist_id}/tracks/append")
async def append_rekordbox_track(playlist_id: str, request: AppendTrackRequest):
    if not request.confirm_update:
        raise HTTPException(400, "Confirm inserting this track into the playlist.")
    track_id = request.track_id.strip()
    if not track_id:
        raise HTTPException(400, "A Rekordbox track ID is required")

    path, plan, _ = local_playlist_with_plan(playlist_id)
    exported = await call_tool(
        "export_playlist",
        {
            "name": path.stem,
            "track_ids": [*plan[0], track_id],
            "update_existing": True,
        },
    )
    if not isinstance(exported, dict):
        raise HTTPException(502, "Unexpected playlist export response.")
    return {
        "name": str(exported.get("name") or path.stem),
        "track_count": int(exported.get("track_count") or len(plan[0]) + 1),
        "updated_existing": bool(exported.get("updated_existing")),
    }
