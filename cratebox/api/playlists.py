"""Playlist parsing, operations, and endpoints."""

from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from urllib.parse import quote

import mutagen
from mutagen.id3 import ID3
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from .artwork_data import embedded_artwork, read_artwork_overrides
from .collection import collection_mcp
from .config import DEFAULT_PLAYLIST_DIR, PLAN_DIRECTORY, PLAYLIST_DIR
from ..core.revision import PlaylistRevision
from ..core.mutations import playlist_mutation_lock

router = APIRouter()
playlist_revision = PlaylistRevision(PLAYLIST_DIR, PLAN_DIRECTORY)

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
    return sorted(
        (p for p in PLAYLIST_DIR.glob("*.m3u*") if p.is_file() and p.suffix.lower() in {".m3u", ".m3u8"}),
        key=lambda p: (p.stem.casefold(), p.name.casefold()),
    )

def playlist_entry_count(lines: list[str]):
    return sum(1 for line in lines if line.strip() and not line.lstrip().startswith("#"))

def read_plan_ids(path: Path, lines: list[str]):
    plan_path = PLAN_DIRECTORY / f"{path.stem}.json"
    if PLAN_DIRECTORY.is_symlink() or plan_path.is_symlink():
        raise HTTPException(409, "The playlist and its track-ID plan are out of sync")
    if not plan_path.exists():
        return plan_path, None
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if not isinstance(plan, dict):
            raise ValueError
        if "tracks" in plan:
            entries = plan["tracks"]
            if not isinstance(entries, list):
                raise ValueError
            track_ids = [entry.get("track_id") for entry in entries if isinstance(entry, dict)]
            if len(track_ids) != len(entries):
                raise ValueError
            file_paths = [entry.get("file_path") for entry in entries if isinstance(entry, dict)]
            if any(
                not isinstance(item, str) or not Path(item).is_absolute()
                or any(character in item for character in "\r\n\x00\x85\u2028\u2029")
                for item in file_paths
            ):
                raise ValueError
        else:
            track_ids = plan.get("track_ids")
            file_paths = None
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        raise HTTPException(409, "The playlist and its track-ID plan are out of sync") from None
    entry_count = playlist_entry_count(lines)
    if (
        not isinstance(track_ids, list)
        or len(track_ids) != entry_count
        or any(not isinstance(track_id, str) or not track_id for track_id in track_ids)
        or (file_paths is not None and len(file_paths) != entry_count)
    ):
        raise HTTPException(409, "The playlist and its track-ID plan are out of sync")
    if file_paths is not None:
        playlist_paths = [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]
        for playlist_path, plan_path_value in zip(playlist_paths, file_paths, strict=True):
            current_path = Path(playlist_path).expanduser()
            if not current_path.is_absolute():
                current_path = path.parent / current_path
            try:
                paths_match = current_path.resolve() == Path(plan_path_value).resolve()
            except (OSError, RuntimeError, ValueError):
                paths_match = False
            if not paths_match:
                raise HTTPException(409, "The playlist and its track-ID plan are out of sync")
    return plan_path, (track_ids, file_paths)

def playlist_entries(
    path: Path,
    lines: list[str],
    plan: tuple[list[str], list[str] | None] | None,
    *,
    include_missing: bool = False,
):
    path_occurrences = {}
    track_occurrences = {}
    entry_number = 0
    for line_number, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        plan_index = entry_number
        rekordbox_id = plan[0][entry_number] if plan else None
        entry_number += 1
        audio = Path(plan[1][plan_index]) if plan and plan[1] else Path(line).expanduser()
        if not audio.is_absolute():
            audio = path.parent / audio
        audio = audio.resolve()
        exists = audio.is_file()
        if not exists and not include_missing:
            continue
        if not exists:
            yield line_number, plan_index, audio, f"{path.stem}-missing-{plan_index}", rekordbox_id
            continue
        audio_key = str(audio)
        if rekordbox_id:
            occurrence = track_occurrences.get(rekordbox_id, 0)
            track_occurrences[rekordbox_id] = occurrence + 1
            row_id = f"{rekordbox_id}-{occurrence + 1}"
        else:
            occurrence = path_occurrences.get(audio_key, 0)
            path_occurrences[audio_key] = occurrence + 1
            digest = hashlib.blake2b(audio_key.encode(), digest_size=8).hexdigest()
            row_id = f"{path.stem}-{digest}-{occurrence}"
        yield line_number, plan_index, audio, row_id, rekordbox_id

def atomic_write(path: Path, content: str):
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
        temporary_path.chmod(path.stat().st_mode)
        os.replace(temporary_path, path)
    except OSError:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
        raise

def mp3_rating(path: Path) -> int:
    """Read a five-star rating from common ID3 rating frames, if present."""
    try:
        tags = ID3(path)
    except (OSError, mutagen.MutagenError):
        return 0

    popularimeters = tags.getall("POPM")
    if popularimeters:
        value = max(int(frame.rating) for frame in popularimeters)
        return min(5, (value * 5 + 127) // 255)

    for frame in tags.getall("TXXX"):
        if frame.desc.strip().casefold() != "rating":
            continue
        try:
            value = float(str(frame.text[0]).strip())
        except (IndexError, TypeError, ValueError):
            continue
        if 0 <= value <= 5:
            return round(value)
        if value <= 100:
            return min(5, round(value / 20))
        return min(5, round(value * 5 / 255))
    return 0

def parse_playlist(path: Path):
    tracks = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        raise HTTPException(500, f"Could not read playlist {path.name}") from exc

    plan_path, plan = read_plan_ids(path, lines)
    plan_tracks = []
    if plan is not None:
        try:
            plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
            plan_tracks = plan_data.get("tracks", []) if isinstance(plan_data, dict) else []
        except (OSError, UnicodeError, json.JSONDecodeError):
            plan_tracks = []
    for _, plan_index, audio, track_id, rekordbox_id in playlist_entries(path, lines, plan):
        try:
            media = mutagen.File(audio, easy=True)
        except (OSError, ValueError):
            media = None
        tags = media or {}
        info = getattr(media, "info", None)

        def tag(key, default=""):
            values = tags.get(key, [])
            return str(values[0]) if values else default

        plan_metadata = (
            plan_tracks[plan_index]
            if plan_index < len(plan_tracks) and isinstance(plan_tracks[plan_index], dict)
            else {}
        )

        def plan_text(key, fallback=""):
            value = plan_metadata.get(key)
            return value.strip() if isinstance(value, str) and value.strip() else fallback

        def plan_number(key, fallback=0, *, integer=False):
            value = plan_metadata.get(key)
            if isinstance(value, bool):
                return fallback
            try:
                number = float(value)
            except (TypeError, ValueError):
                return fallback
            if not math.isfinite(number):
                return fallback
            return int(number) if integer else number

        try:
            audio_bpm = float(tag("bpm", "0") or 0)
        except (TypeError, ValueError):
            audio_bpm = 0
        bitrate = getattr(info, "bitrate", 0) or 0
        plan_rating = plan_number("rating", -1, integer=True)
        plan_playlists = plan_metadata.get("playlists")
        playlists = [
            {"id": item["id"], "name": item["name"]}
            for item in plan_playlists
            if isinstance(item, dict) and isinstance(item.get("id"), str)
            and isinstance(item.get("name"), str)
        ] if isinstance(plan_playlists, list) else []
        tracks.append({
            "id": track_id,
            "playlist_id": path.stem,
            "rekordbox_id": rekordbox_id,
            "title": plan_text("title", tag("title", audio.stem)),
            "artist": plan_text("artist", tag("artist")),
            "album": plan_text("album", tag("album")),
            "genre": plan_text("genre"),
            "duration": plan_number("duration", round(getattr(info, "length", 0) or 0), integer=True),
            "rating": plan_rating if 0 < plan_rating <= 5 else (
                mp3_rating(audio) if audio.suffix.lower() == ".mp3" else 0
            ),
            "play_count": plan_number("play_count", 0, integer=True),
            "cue_count": plan_number("cue_count", 0, integer=True),
            "playlist_count": plan_number("playlist_count", len(playlists), integer=True),
            "playlists": playlists,
            "bpm": plan_number("bpm", audio_bpm) or audio_bpm,
            "key": plan_text("key", tag("initialkey")),
            "quality": f"{audio.suffix[1:].upper()} {bitrate // 1000}kbps".strip(),
            "url": f"/api/stream?playlist_id={quote(path.stem)}&track_id={quote(track_id)}",
            "artwork_url": f"/api/playlists/{quote(path.stem)}/tracks/{quote(track_id)}/artwork",
            "has_artwork": embedded_artwork(audio) is not None,
        })
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
    matches = [p for p in playlist_files() if p.stem == playlist_id]
    if not matches:
        raise HTTPException(404, "Playlist not found")
    return matches[0]

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
    name = request.name.strip()
    if (
        not name or name in (".", "..") or len(name.encode("utf-8")) > 200
        or any(character in name for character in "/\\") or not name.isprintable()
    ):
        raise HTTPException(400, "Use a playlist name of up to 200 UTF-8 bytes without path separators or control characters.")
    if (
        DEFAULT_PLAYLIST_DIR.is_symlink() or PLAYLIST_DIR != DEFAULT_PLAYLIST_DIR
        or PLAN_DIRECTORY.is_symlink()
    ):
        raise HTTPException(403, "Playlist creation is limited to the app's playlists and output folders")

    path = PLAYLIST_DIR / f"{name}.m3u8"
    plan_path = PLAN_DIRECTORY / f"{name}.json"
    if (
        any(item.stem.casefold() == name.casefold() for item in playlist_files())
        or plan_path.exists()
        or plan_path.is_symlink()
    ):
        raise HTTPException(409, "A playlist with this name already exists")

    playlist_created = False
    plan_created = False
    try:
        with path.open("x", encoding="utf-8", newline="\n") as playlist:
            playlist.write("#EXTM3U\n")
        playlist_created = True
        with plan_path.open("x", encoding="utf-8", newline="\n") as plan_file:
            plan_created = True
            json.dump({"format": 1, "name": name, "tracks": []}, plan_file, ensure_ascii=False, indent=2)
            plan_file.write("\n")
    except FileExistsError:
        if playlist_created:
            path.unlink(missing_ok=True)
        raise HTTPException(409, "A playlist with this name already exists") from None
    except OSError as exc:
        if playlist_created:
            path.unlink(missing_ok=True)
        if plan_created:
            plan_path.unlink(missing_ok=True)
        raise HTTPException(500, "Could not create the playlist") from exc

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
    if DEFAULT_PLAYLIST_DIR.is_symlink() or PLAYLIST_DIR != DEFAULT_PLAYLIST_DIR:
        raise HTTPException(403, "Playlist edits are limited to the app's playlists folder")
    if not track_ids or len(track_ids) > 1000 or len(set(track_ids)) != len(track_ids):
        raise HTTPException(400, "Select between 1 and 1000 unique tracks")

    path = find_playlist(playlist_id)
    try:
        with path.open(encoding="utf-8-sig", newline="") as playlist:
            lines = playlist.readlines()
    except (OSError, UnicodeError) as exc:
        raise HTTPException(500, "Could not read playlist") from exc

    plan_path, plan = read_plan_ids(path, lines)
    plan_data = None
    if plan_path.is_file():
        if plan is None or plan_path.is_symlink() or PLAN_DIRECTORY.is_symlink():
            raise HTTPException(409, "The playlist and its track-ID plan are out of sync")
        plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
    entries = {
        track_id: (line_number, plan_index)
        for line_number, plan_index, _, track_id, _ in playlist_entries(path, lines, plan)
    }
    remove_indices = set()
    remove_plan_indices = set()
    for track_id in track_ids:
        if track_id not in entries:
            raise HTTPException(404, "Track not found in playlist")
        index, plan_index = entries[track_id]
        remove_indices.add(index)
        remove_plan_indices.add(plan_index)
        if index and lines[index - 1].lstrip().startswith("#EXTINF:"):
            remove_indices.add(index - 1)

    updated_lines = [line for index, line in enumerate(lines) if index not in remove_indices]
    if plan_data is not None:
        if isinstance(plan_data.get("tracks"), list):
            plan_data["tracks"] = [
                entry for index, entry in enumerate(plan_data["tracks"])
                if index not in remove_plan_indices
            ]
        else:
            plan_data["track_ids"] = [
                track_id for index, track_id in enumerate(plan_data["track_ids"])
                if index not in remove_plan_indices
            ]
    original_text = "".join(lines)
    playlist_updated = False
    try:
        atomic_write(path, "".join(updated_lines))
        playlist_updated = True
        if plan_data is not None:
            plan_text = json.dumps(plan_data, ensure_ascii=False, indent=2) + "\n"
            atomic_write(plan_path, plan_text)
    except OSError as exc:
        if playlist_updated:
            try:
                atomic_write(path, original_text)
            except OSError:
                raise HTTPException(500, "Playlist and track-ID plan may be out of sync") from None
        raise HTTPException(500, "Could not update playlist") from exc
    return {"removed": len(track_ids)}

@router.post("/api/playlists/{playlist_id}/tracks/swap")
async def swap_track(playlist_id: str, request: PlaylistSwap):
    async with playlist_mutation_lock(playlist_id):
        return _swap_track(playlist_id, request)


def _swap_track(playlist_id: str, request: PlaylistSwap):
    if DEFAULT_PLAYLIST_DIR.is_symlink() or PLAYLIST_DIR != DEFAULT_PLAYLIST_DIR:
        raise HTTPException(403, "Playlist edits are limited to the app's playlists folder")
    if not request.source_track_id or not request.replacement_track_id:
        raise HTTPException(400, "Both playlist and replacement track IDs are required")
    replacement_audio = collection_mcp.track_paths.get(request.replacement_track_id)
    if replacement_audio is None or not replacement_audio.is_file():
        raise HTTPException(404, "Replacement track is unavailable; run lookup again")

    path = find_playlist(playlist_id)
    try:
        with path.open(encoding="utf-8-sig", newline="") as playlist:
            lines = playlist.readlines()
    except (OSError, UnicodeError) as exc:
        raise HTTPException(500, "Could not read playlist") from exc

    plan_path, plan = read_plan_ids(path, lines)
    entries = list(playlist_entries(path, lines, plan))
    source = next(
        (entry for entry in entries if entry[3] == request.source_track_id), None,
    )
    if source is None:
        raise HTTPException(404, "Source track not found in playlist")
    line_number, plan_index = source[0], source[1]
    original_text = "".join(lines)
    line_ending = "\r\n" if lines[line_number].endswith("\r\n") else "\n" if lines[line_number].endswith("\n") else ""
    lines[line_number] = f"{replacement_audio}{line_ending}"

    plan_data = None
    if plan_path.is_file():
        if plan is None or plan_path.is_symlink() or PLAN_DIRECTORY.is_symlink():
            raise HTTPException(409, "The playlist and its track-ID plan are out of sync")
        try:
            plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
            if isinstance(plan_data.get("tracks"), list):
                plan_item = plan_data["tracks"][plan_index]
                plan_item["track_id"] = request.replacement_track_id
                plan_item["file_path"] = str(replacement_audio)
                for metadata_key in (
                    "title", "artist", "album", "genre", "bpm", "key", "rating",
                    "duration", "bitrate", "sample_rate",
                    "play_count", "cue_count", "playlist_count", "playlists",
                ):
                    plan_item.pop(metadata_key, None)
            else:
                plan_data["track_ids"][plan_index] = request.replacement_track_id
        except (AttributeError, IndexError, KeyError, TypeError, OSError, UnicodeError, json.JSONDecodeError):
            raise HTTPException(409, "The playlist and its track-ID plan are out of sync") from None

    playlist_updated = False
    try:
        atomic_write(path, "".join(lines))
        playlist_updated = True
        if plan_data is not None:
            atomic_write(plan_path, json.dumps(plan_data, ensure_ascii=False, indent=2) + "\n")
    except OSError as exc:
        if playlist_updated:
            try:
                atomic_write(path, original_text)
            except OSError:
                raise HTTPException(500, "Playlist and track-ID plan may be out of sync") from None
        raise HTTPException(500, "Could not update playlist") from exc

    updated_plan = None
    if plan is not None:
        track_ids = list(plan[0])
        track_ids[plan_index] = request.replacement_track_id
        file_paths = list(plan[1]) if plan[1] is not None else None
        if file_paths is not None:
            file_paths[plan_index] = str(replacement_audio)
        updated_plan = (track_ids, file_paths)
    updated_entries = playlist_entries(path, lines, updated_plan)
    updated_track = next((entry for entry in updated_entries if entry[1] == plan_index), None)
    return {"track_id": updated_track[3] if updated_track else None}


@router.post("/api/playlists/{playlist_id}/tracks/reorder")
async def reorder_track(playlist_id: str, request: PlaylistReorder):
    async with playlist_mutation_lock(playlist_id):
        return _reorder_track(playlist_id, request)


def _reorder_track(playlist_id: str, request: PlaylistReorder):
    if DEFAULT_PLAYLIST_DIR.is_symlink() or PLAYLIST_DIR != DEFAULT_PLAYLIST_DIR:
        raise HTTPException(403, "Playlist edits are limited to the app's playlists folder")
    source_track_ids = request.source_track_ids
    if source_track_ids is None:
        source_track_ids = [request.source_track_id] if request.source_track_id else []
    if (
        not source_track_ids or len(source_track_ids) > 1000
        or any(not track_id for track_id in source_track_ids)
        or len(set(source_track_ids)) != len(source_track_ids)
        or not request.target_track_id
    ):
        raise HTTPException(400, "Valid source and target playlist track IDs are required")

    path = find_playlist(playlist_id)
    try:
        with path.open(encoding="utf-8-sig", newline="") as playlist:
            lines = playlist.readlines()
    except (OSError, UnicodeError) as exc:
        raise HTTPException(500, "Could not read playlist") from exc

    plan_path, plan = read_plan_ids(path, lines)
    original_entries = list(playlist_entries(path, lines, plan, include_missing=True))
    entries = list(original_entries)
    source_ids = set(source_track_ids)
    source_entries = [entry for entry in entries if entry[3] in source_ids]
    target_entry = next((entry for entry in entries if entry[3] == request.target_track_id), None)
    if len(source_entries) != len(source_ids) or target_entry is None:
        raise HTTPException(404, "Track not found in playlist")
    if request.target_track_id in source_ids:
        return {"moved": False}
    entries = [entry for entry in entries if entry[3] not in source_ids]
    target_index = next(i for i, entry in enumerate(entries) if entry[0] == target_entry[0])
    entries[target_index + (0 if request.before else 1):target_index + (0 if request.before else 1)] = source_entries

    first_line = original_entries[0][0]
    if first_line > 0 and lines[first_line - 1].lstrip().startswith("#EXTINF:"):
        first_line -= 1
    header = lines[:first_line]
    blocks = []
    previous_line = first_line - 1
    for entry in original_entries:
        line_number = entry[0]
        blocks.append(lines[previous_line + 1:line_number + 1])
        previous_line = line_number
    suffix = lines[previous_line + 1:]
    blocks_by_line = {
        entry[0]: block
        for entry, block in zip(original_entries, blocks, strict=True)
    }
    updated_lines = header + [line for entry in entries for line in blocks_by_line[entry[0]]] + suffix

    plan_data = None
    if plan_path.is_file():
        if plan is None or plan_path.is_symlink() or PLAN_DIRECTORY.is_symlink():
            raise HTTPException(409, "The playlist and its track-ID plan are out of sync")
        try:
            plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
            plan_order = [entry[1] for entry in entries]
            if isinstance(plan_data.get("tracks"), list):
                plan_data["tracks"] = [plan_data["tracks"][index] for index in plan_order]
            else:
                plan_data["track_ids"] = [plan_data["track_ids"][index] for index in plan_order]
        except (AttributeError, IndexError, KeyError, TypeError, OSError, UnicodeError, json.JSONDecodeError):
            raise HTTPException(409, "The playlist and its track-ID plan are out of sync") from None

    original_text = "".join(lines)
    playlist_updated = False
    try:
        atomic_write(path, "".join(updated_lines))
        playlist_updated = True
        if plan_data is not None:
            atomic_write(plan_path, json.dumps(plan_data, ensure_ascii=False, indent=2) + "\n")
    except OSError as exc:
        if playlist_updated:
            try:
                atomic_write(path, original_text)
            except OSError:
                raise HTTPException(500, "Playlist and track-ID plan may be out of sync") from None
        raise HTTPException(500, "Could not update playlist") from exc
    return {"moved": True}

