"""Direct Rekordbox playlist browsing/editing and local playlist operations."""

import json
import logging
from pathlib import Path
from typing import Literal

import mutagen
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .artwork_data import embedded_artwork
from .collection import collection_mcp
from .config import DEFAULT_PLAYLIST_DIR, CRATE_DIRECTORY, PLAYLIST_DIR
from .playlists import playlist_mutation_lock
from core.collection import CollectionConnectionError
from core.export import export_playlist as core_export_playlist
from core.audio_metadata import read_embedded_rating
from core.crates import (
    ApplicationError,
    append_crate_tracks as core_append_crate_tracks,
    insert_crate_separator as core_insert_crate_separator,
    insert_crate_track as core_insert_crate_track,
    replace_crate_separator as core_replace_crate_separator,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class PlaylistEdit(BaseModel):
    action: Literal['rename', 'add', 'remove', 'swap', 'move']
    expected_revision: str = Field(min_length=1)
    name: str | None = None
    entry_ids: list[str] | None = None
    track_ids: list[str] | None = None
    position: int | None = None
    target_entry_id: str | None = None
    before: bool = True


class RekordboxPlaylistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class CopyPlaylistRequest(BaseModel):
    name: str
    update_existing: bool = False


class InsertSeparatorRequest(BaseModel):
    type: Literal["generic", "90s", "R&B", "Ambi", "Salsa", "Party", "Dance"]
    after_track_id: str
    confirm_update: bool = False


class ReplaceSeparatorRequest(BaseModel):
    type: Literal["generic", "90s", "R&B", "Ambi", "Salsa", "Party", "Dance"]
    separator_row_id: str
    confirm_update: bool = False


class AppendTrackRequest(BaseModel):
    track_id: str
    confirm_update: bool = False


class AppendTracksRequest(BaseModel):
    track_ids: list[str]
    confirm_update: bool = False


class InsertTrackRequest(BaseModel):
    track_id: str
    after_track_id: str
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
    try:
        result = await collection_mcp.call_tool(name, arguments or {})
    except HTTPException:
        raise
    except CollectionConnectionError as error:
        raise HTTPException(error.status_code, error.detail) from None
    except Exception:
        logger.exception("Rekordbox MCP tool call failed (%s)", name)
        raise HTTPException(502, "Rekordbox playlist request failed.") from None
    if result.is_error:
        message = next((item.text for item in result.content if hasattr(item, "text")), "")
        logger.error("Rekordbox MCP tool returned an error (%s): %s", name, message)
        if name in {'edit_playlist', 'get_playlist_state', 'get_playlist_tracks', 'get_playlists'}:
            safe_errors = [
                ('close rekordbox', 409, 'Close Rekordbox and its background agents to access the collection.'),
                ('process inspection', 503, 'Cannot verify Rekordbox is closed. Try again after closing it and its agents.'),
                ('playlist changed', 409, 'Playlist changed; reload it before editing.'),
                ('busy', 409, 'Rekordbox database is busy. Try the action again.'),
                ('backup', 503, 'A verified database backup is unavailable. The edit was blocked.'),
                ('recovery required', 503, 'Database recovery required. Inspect and restore a verified backup before editing.'),
                ('smart playlist', 400, 'Folders and smart playlists cannot be edited.'),
                ('playlist not found', 404, 'Rekordbox playlist not found.'),
                ('track is not active', 409, 'Track is no longer active in the collection.'),
            ]
            for needle, code, detail in safe_errors:
                if needle in message.lower():
                    raise HTTPException(code, detail)
        if "already exists" in message.lower():
            raise HTTPException(409, "A CrateBox playlist with this name already exists.")
        if name == "get_collection_tracks":
            raise HTTPException(409, "One or more playlist tracks no longer match the Rekordbox collection.")
        raise HTTPException(502, "Rekordbox playlist request failed.")
    try:
        return result_value(result)
    except (IndexError, TypeError, json.JSONDecodeError):
        raise HTTPException(502, "Unexpected response from Rekordbox.") from None


async def export_local_playlist(
    name: str,
    *,
    track_ids: list[str] | None = None,
    file_paths: list[str] | None = None,
    update_existing: bool = False,
    separators: list[dict] | None = None,
):
    async def resolve_tracks(**selector):
        try:
            result = await collection_mcp.call_tool("get_collection_tracks", selector)
        except CollectionConnectionError as error:
            raise HTTPException(error.status_code, error.detail) from None
        if result.is_error:
            raise HTTPException(409, "One or more tracks no longer resolve to the active collection snapshot.")
        value = result_value(result)
        if not isinstance(value, list):
            raise HTTPException(502, "Unexpected collection track response.")
        return value

    try:
        return await core_export_playlist(
            name,
            track_ids=track_ids,
            file_paths=file_paths,
            resolve_tracks=resolve_tracks,
            update_existing=update_existing,
            separators=separators,
        )
    except HTTPException:
        raise
    except FileExistsError as error:
        raise HTTPException(409, str(error)) from None
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    except OSError:
        logger.exception("CrateBox playlist export could not write the paired artifacts")
        raise HTTPException(500, "Cannot write the playlist and plan files.") from None
    except Exception:
        logger.exception("CrateBox playlist export failed")
        raise HTTPException(502, "Playlist export failed.") from None


async def apply_crate_operation(operation, *args):
    async def resolve_tracks(**selector):
        return await call_tool("get_collection_tracks", selector)

    try:
        return await operation(
            *args, resolve_tracks, PLAYLIST_DIR, CRATE_DIRECTORY, DEFAULT_PLAYLIST_DIR,
        )
    except HTTPException:
        raise
    except ApplicationError as error:
        raise HTTPException(error.status_code, error.detail) from None
    except FileExistsError as error:
        raise HTTPException(409, str(error)) from None
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    except OSError:
        logger.exception("CrateBox playlist operation could not write the paired artifacts")
        raise HTTPException(500, "Cannot write the playlist and plan files.") from None
    except Exception:
        logger.exception("CrateBox playlist operation failed")
        raise HTTPException(502, "Playlist operation failed.") from None


async def playlist_records():
    records = await call_tool("get_playlists")
    if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
        raise HTTPException(502, "Unexpected Rekordbox playlist list.")
    return records


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
    track_ids = [str(record["id"]) for record in records if record.get("id") is not None]
    locations = await call_tool("get_collection_tracks", {"track_ids": track_ids}) if track_ids else []
    if not isinstance(locations, list) or len(locations) != len(track_ids):
        raise HTTPException(502, "Unexpected Rekordbox track locations.")
    for track_id, location in zip(track_ids, locations, strict=True):
        if (
            not isinstance(location, dict)
            or str(location.get("id")) != track_id
            or not isinstance(location.get("file_path"), str)
            or not Path(location["file_path"]).is_absolute()
            or any(character in location["file_path"] for character in "\r\n\x00\x85\u2028\u2029")
        ):
            raise HTTPException(502, "Unexpected Rekordbox track locations.")
        collection_mcp.track_paths[track_id] = Path(location["file_path"])

    for record in records:
        if record.get("id") is None:
            continue
        rekordbox_id = str(record["id"])
        occurrence = occurrences.get(rekordbox_id, 0)
        occurrences[rekordbox_id] = occurrence + 1
        audio_path = collection_mcp.track_paths[rekordbox_id]
        try:
            media = mutagen.File(audio_path, easy=True)
        except (OSError, ValueError, mutagen.MutagenError):
            media = None
        bitrate = getattr(getattr(media, "info", None), "bitrate", 0) or 0
        audio_format = audio_path.suffix[1:].upper()
        quality = f"{audio_format} {bitrate // 1000}kbps" if bitrate else audio_format
        rekordbox_rating = int(record.get("rating") or 0)
        file_rating = read_embedded_rating(
            audio_path,
            fallback=rekordbox_rating if 0 < rekordbox_rating <= 5 else None,
        )
        tracks.append({
            "id": str(record.get("playlist_entry_id") or f"{rekordbox_id}-{occurrence + 1}"),
            "rekordbox_id": rekordbox_id,
            "title": str(record.get("title") or ""),
            "artist": str(record.get("artist") or ""),
            "album": str(record.get("album") or ""),
            "duration": int(record.get("length") or 0),
            "rating": file_rating if file_rating is not None else rekordbox_rating,
            "play_count": int(record.get("play_count") or 0),
            "cue_count": int(record.get("cue_count") or 0),
            "playlist_count": int(record.get("playlist_count") or 0),
            "playlists": [
                {"id": str(item.get("id") or ""), "name": str(item.get("name") or "")}
                for item in (record.get("playlists") or [])
                if isinstance(item, dict) and item.get("id") is not None
            ],
            "bpm": float(record.get("bpm") or 0),
            "key": str(record.get("key") or ""),
            "quality": quality,
            "url": "",
            "has_artwork": embedded_artwork(audio_path) is not None,
        })
    return tracks


@router.get('/api/rekordbox/playlists/{playlist_id}/detail')
async def get_rekordbox_playlist_detail(playlist_id: str):
    state = await call_tool('get_playlist_state', {'playlist_id': playlist_id})
    tracks = await get_rekordbox_playlist_tracks(playlist_id)
    after = await call_tool('get_playlist_state', {'playlist_id': playlist_id})
    if state.get('revision') != after.get('revision') or [
        (track['id'], track['rekordbox_id']) for track in tracks
    ] != [(entry['entry_id'], entry['track_id']) for entry in state['entries']]:
        raise HTTPException(409, 'Playlist changed; reload it before editing.')
    return {'id': state['id'], 'name': state.get('name', ''),
            'revision': state['revision'], 'editable': state.get('editable', False), 'tracks': tracks}


@router.post('/api/rekordbox/playlists')
async def create_rekordbox_playlist(request: RekordboxPlaylistCreate):
    return await call_tool('edit_playlist', {'action': 'create', 'name': request.name})


@router.post('/api/rekordbox/playlists/{playlist_id}/edit')
async def edit_rekordbox_playlist(playlist_id: str, request: PlaylistEdit):
    return await call_tool('edit_playlist', {'playlist_id': playlist_id, **request.model_dump()})


@router.post("/api/rekordbox/playlists/{playlist_id}/copy")
async def copy_rekordbox_playlist(playlist_id: str, request: CopyPlaylistRequest):
    name = request.name.strip()
    if not name:
        raise HTTPException(400, "Enter a name for the CrateBox copy.")

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

    async with playlist_mutation_lock(name):
        exported = await export_local_playlist(
            name, track_ids=track_ids, update_existing=request.update_existing,
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
    async with playlist_mutation_lock(playlist_id):
        exported = await apply_crate_operation(
            core_insert_crate_separator, playlist_id, request.type, request.after_track_id,
        )
        if not isinstance(exported, dict):
            raise HTTPException(502, "Unexpected playlist export response.")
        return {
            "name": str(exported.get("name") or playlist_id),
            "track_count": int(exported.get("track_count") or 0),
            "separator_count": int(exported.get("separator_count") or 0),
            "updated_existing": bool(exported.get("updated_existing")),
        }


@router.post("/api/playlists/{playlist_id}/separators/replace")
async def replace_playlist_separator(playlist_id: str, request: ReplaceSeparatorRequest):
    if not request.confirm_update:
        raise HTTPException(400, "Confirm updating this playlist before replacing a separator.")
    async with playlist_mutation_lock(playlist_id):
        return await apply_crate_operation(
            core_replace_crate_separator,
            playlist_id, request.separator_row_id, request.type,
        )


@router.post("/api/playlists/{playlist_id}/tracks/append")
async def append_rekordbox_track(playlist_id: str, request: AppendTrackRequest):
    return await append_rekordbox_tracks(
        playlist_id,
        AppendTracksRequest(track_ids=[request.track_id], confirm_update=request.confirm_update),
    )


@router.post("/api/playlists/{playlist_id}/tracks/append-many")
async def append_rekordbox_tracks(playlist_id: str, request: AppendTracksRequest):
    if not request.confirm_update:
        raise HTTPException(400, "Confirm inserting this track into the playlist.")
    async with playlist_mutation_lock(playlist_id):
        exported = await apply_crate_operation(
            core_append_crate_tracks, playlist_id, request.track_ids,
        )
        if not isinstance(exported, dict):
            raise HTTPException(502, "Unexpected playlist export response.")
        return {
            "name": str(exported.get("name") or playlist_id),
            "track_count": int(exported.get("track_count") or 0),
            "updated_existing": bool(exported.get("updated_existing")),
        }


@router.post("/api/playlists/{playlist_id}/tracks/insert-after")
async def insert_rekordbox_track(playlist_id: str, request: InsertTrackRequest):
    if not request.confirm_update:
        raise HTTPException(400, "Confirm inserting this track into the playlist.")
    async with playlist_mutation_lock(playlist_id):
        result = await apply_crate_operation(
            core_insert_crate_track, playlist_id, request.track_id, request.after_track_id,
        )
        exported = result["export"]
        if not isinstance(exported, dict):
            raise HTTPException(502, "Unexpected playlist export response.")
        return {
            "track_id": result["track_id"],
            "name": str(exported.get("name") or playlist_id),
            "track_count": int(exported.get("track_count") or 0),
            "updated_existing": bool(exported.get("updated_existing")),
        }
