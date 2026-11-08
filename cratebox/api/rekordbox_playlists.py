"""Read-only Rekordbox playlist browsing and local playlist operations."""

import json
import logging
from pathlib import Path
from typing import Literal

import mutagen
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .artwork_data import embedded_artwork
from .collection import collection_mcp
from .config import DEFAULT_PLAYLIST_DIR, PLAN_DIRECTORY, PLAYLIST_DIR
from .playlists import (
    atomic_write,
    playlist_entries,
    playlist_files,
    playlist_mutation_lock,
    read_plan_ids,
)
from core.export import export_playlist as core_export_playlist

router = APIRouter()
logger = logging.getLogger(__name__)


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


SEPARATOR_TRACK_TYPES = {
    "228753448": "generic",
    "118082420": "90s",
    "38579759": "R&B",
    "242295304": "Ambi",
    "244354734": "Salsa",
    "247266859": "Party",
    "32984962": "Dance",
}
SEPARATOR_TRACK_FILES = {
    "generic": "Separator.wav",
    "90s": "Separator-90.wav",
    "R&B": "Separator-RB.wav",
    "Ambi": "Separator-Ambi.wav",
    "Salsa": "Separator-Salsa.wav",
    "Party": "Separator-Party.wav",
    "Dance": "Separator-Dance.wav",
}


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
    except Exception:
        logger.exception("Rekordbox MCP tool call failed (%s)", name)
        raise HTTPException(502, "Rekordbox playlist request failed.") from None
    if result.is_error:
        message = next((item.text for item in result.content if hasattr(item, "text")), "")
        logger.error("Rekordbox MCP tool returned an error (%s): %s", name, message)
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
        result = await collection_mcp.call_tool("get_collection_tracks", selector)
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


async def validate_plan_locations(plan):
    track_ids, file_paths = plan
    locations = await call_tool("get_collection_tracks", {"track_ids": track_ids})
    if not isinstance(locations, list) or len(locations) != len(track_ids):
        raise HTTPException(409, "The playlist and its track-ID plan are out of sync")
    try:
        for track_id, file_path, location in zip(track_ids, file_paths, locations, strict=True):
            if (
                not isinstance(location, dict)
                or str(location.get("id")) != track_id
                or Path(location.get("file_path", "")).resolve() != Path(file_path).resolve()
            ):
                raise HTTPException(409, "The playlist and its track-ID plan are out of sync")
    except (OSError, RuntimeError, TypeError, ValueError):
        raise HTTPException(409, "The playlist and its track-ID plan are out of sync") from None


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
        tracks.append({
            "id": f"{rekordbox_id}-{occurrence + 1}",
            "rekordbox_id": rekordbox_id,
            "title": str(record.get("title") or ""),
            "artist": str(record.get("artist") or ""),
            "album": str(record.get("album") or ""),
            "duration": int(record.get("length") or 0),
            "rating": int(record.get("rating") or 0),
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
        path, plan, lines = local_playlist_with_plan(playlist_id)
        await validate_plan_locations(plan)
        entries = list(playlist_entries(path, lines, plan))
        target = next((entry for entry in entries if entry[3] == request.after_track_id), None)
        if target is None:
            raise HTTPException(404, "Selected track not found in playlist")

        exported = await export_local_playlist(
            path.stem,
            track_ids=plan[0],
            update_existing=True,
            separators=[{"type": request.type, "before_track": target[1] + 2}],
        )
        if not isinstance(exported, dict):
            raise HTTPException(502, "Unexpected playlist export response.")
        return {
            "name": str(exported.get("name") or path.stem),
            "track_count": int(exported.get("track_count") or len(plan[0])),
            "separator_count": int(exported.get("separator_count") or 0),
            "updated_existing": bool(exported.get("updated_existing")),
        }


@router.post("/api/playlists/{playlist_id}/separators/replace")
async def replace_playlist_separator(playlist_id: str, request: ReplaceSeparatorRequest):
    if not request.confirm_update:
        raise HTTPException(400, "Confirm updating this playlist before replacing a separator.")
    if not request.separator_row_id:
        raise HTTPException(400, "A separator row ID is required.")

    async with playlist_mutation_lock(playlist_id):
        path, plan, lines = local_playlist_with_plan(playlist_id)
        separator_occurrences: dict[str, int] = {}
        target_entry = None
        plan_index = None
        for plan_index, track_id in enumerate(plan[0]):
            if track_id in SEPARATOR_TRACK_TYPES:
                occurrence = separator_occurrences.get(track_id, 0) + 1
                separator_occurrences[track_id] = occurrence
                row_id = f"{track_id}-{occurrence}"
                if row_id == request.separator_row_id:
                    target_entry = next(
                        (
                            entry for entry in playlist_entries(path, lines, plan)
                            if entry[3] == row_id
                        ),
                        None,
                    )
                    break

        if plan_index is None or target_entry is None:
            raise HTTPException(404, "Separator not found in playlist.")

        replacement_track_id = next(
            track_id for track_id, separator_type in SEPARATOR_TRACK_TYPES.items()
            if separator_type == request.type
        )
        locations = await call_tool(
            "get_collection_tracks",
            {"track_ids": [plan[0][plan_index], replacement_track_id]},
        )
        if (
            not isinstance(locations, list)
            or len(locations) != 2
            or any(not isinstance(item, dict) for item in locations)
            or str(locations[0].get("id")) != plan[0][plan_index]
            or str(locations[1].get("id")) != replacement_track_id
        ):
            raise HTTPException(502, "Unexpected Rekordbox track locations.")
        try:
            current_path = Path(locations[0]["file_path"])
            replacement_path = Path(locations[1]["file_path"])
            if (
                current_path.resolve() != Path(plan[1][plan_index]).resolve()
                or not replacement_path.is_absolute()
                or not replacement_path.is_file()
                or replacement_path.name != SEPARATOR_TRACK_FILES[request.type]
                or replacement_path.resolve().parent != current_path.resolve().parent
            ):
                raise HTTPException(409, "The separator and its track-ID plan are out of sync")
        except (KeyError, OSError, RuntimeError, TypeError, ValueError):
            raise HTTPException(409, "The separator and its track-ID plan are out of sync") from None

        plan_path = PLAN_DIRECTORY / f"{path.stem}.json"
        try:
            plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
            plan_items = plan_data["tracks"]
            if not isinstance(plan_items[plan_index], dict):
                raise ValueError
            plan_items[plan_index]["track_id"] = replacement_track_id
            plan_items[plan_index]["file_path"] = str(replacement_path)
            plan_items[plan_index]["separator_type"] = request.type
        except (
            AttributeError,
            IndexError,
            KeyError,
            TypeError,
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            ValueError,
        ):
            raise HTTPException(409, "The playlist and its track-ID plan are out of sync") from None

        line_number = target_entry[0]
        old_playlist_text = "".join(lines)
        line_ending = (
            "\r\n" if lines[line_number].endswith("\r\n")
            else "\n" if lines[line_number].endswith("\n") else ""
        )
        lines[line_number] = f"{replacement_path}{line_ending}"
        plan_text = json.dumps(plan_data, ensure_ascii=False, indent=2) + "\n"
        playlist_updated = False
        try:
            atomic_write(path, "".join(lines))
            playlist_updated = True
            atomic_write(plan_path, plan_text)
        except OSError as exc:
            if playlist_updated:
                try:
                    atomic_write(path, old_playlist_text)
                except OSError:
                    raise HTTPException(500, "Playlist and track-ID plan may be out of sync") from None
            raise HTTPException(500, "Could not update playlist") from exc

        separator_count = sum(item in SEPARATOR_TRACK_TYPES for item in plan[0])
        return {
            "name": path.stem,
            "track_count": len(plan[0]) - separator_count,
            "separator_count": separator_count,
            "updated_existing": True,
        }


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
    track_ids = [track_id.strip() for track_id in request.track_ids]
    if not track_ids or any(not track_id for track_id in track_ids):
        raise HTTPException(400, "At least one Rekordbox track ID is required")

    async with playlist_mutation_lock(playlist_id):
        path, plan, _ = local_playlist_with_plan(playlist_id)
        await validate_plan_locations(plan)
        exported = await export_local_playlist(
            path.stem, track_ids=[*plan[0], *track_ids], update_existing=True,
        )
        if not isinstance(exported, dict):
            raise HTTPException(502, "Unexpected playlist export response.")
        return {
            "name": str(exported.get("name") or path.stem),
            "track_count": int(exported.get("track_count") or len(plan[0]) + len(track_ids)),
            "updated_existing": bool(exported.get("updated_existing")),
        }


@router.post("/api/playlists/{playlist_id}/tracks/insert-after")
async def insert_rekordbox_track(playlist_id: str, request: InsertTrackRequest):
    if not request.confirm_update:
        raise HTTPException(400, "Confirm inserting this track into the playlist.")
    track_id = request.track_id.strip()
    after_track_id = request.after_track_id.strip()
    if not track_id or not after_track_id:
        raise HTTPException(400, "Both Rekordbox track IDs are required")

    async with playlist_mutation_lock(playlist_id):
        path, plan, lines = local_playlist_with_plan(playlist_id)
        await validate_plan_locations(plan)
        target = next(
            (
                entry
                for entry in playlist_entries(path, lines, plan, include_missing=True)
                if entry[3] == after_track_id
            ),
            None,
        )
        if target is None:
            raise HTTPException(404, "Selected track not found in playlist")

        insertion_index = target[1] + 1
        track_ids = [*plan[0][:insertion_index], track_id, *plan[0][insertion_index:]]
        exported = await export_local_playlist(
            path.stem, track_ids=track_ids, update_existing=True,
        )
        if not isinstance(exported, dict):
            raise HTTPException(502, "Unexpected playlist export response.")
        occurrence = track_ids[:insertion_index].count(track_id) + 1
        return {
            "track_id": f"{track_id}-{occurrence}",
            "name": str(exported.get("name") or path.stem),
            "track_count": int(exported.get("track_count") or len(track_ids)),
            "updated_existing": bool(exported.get("updated_existing")),
        }
