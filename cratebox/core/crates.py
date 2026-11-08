"""Crate file discovery and playlist-to-crate reference parsing."""

import hashlib
import json
import math
import os
from pathlib import Path
import tempfile


class ApplicationError(Exception):
    def __init__(self, detail: str, status_code: int = 500):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class ApplicationConflict(ApplicationError):
    def __init__(self, detail: str):
        super().__init__(detail, 409)


class ApplicationValidationError(ApplicationError):
    def __init__(self, detail: str):
        super().__init__(detail, 400)


class ApplicationForbidden(ApplicationError):
    def __init__(self, detail: str):
        super().__init__(detail, 403)


class ApplicationNotFound(ApplicationError):
    def __init__(self, detail: str):
        super().__init__(detail, 404)


def playlist_files(directory: Path) -> list[Path]:
    return sorted(
        (path for path in Path(directory).glob("*.m3u*")
         if path.is_file() and path.suffix.lower() in {".m3u", ".m3u8"}),
        key=lambda path: (path.stem.casefold(), path.name.casefold()),
    )


def playlist_entry_count(lines: list[str]) -> int:
    return sum(1 for line in lines if line.strip() and not line.lstrip().startswith("#"))


def read_plan_ids(path: Path, lines: list[str], crate_directory: Path):
    crate_directory = Path(crate_directory)
    plan_path = crate_directory / f"{path.stem}.json"
    if crate_directory.is_symlink() or crate_directory.parent.is_symlink() or plan_path.is_symlink():
        raise ApplicationConflict("The playlist and its track-ID plan are out of sync")
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
        raise ApplicationConflict("The playlist and its track-ID plan are out of sync") from None

    entry_count = playlist_entry_count(lines)
    if (
        not isinstance(track_ids, list)
        or len(track_ids) != entry_count
        or any(not isinstance(track_id, str) or not track_id for track_id in track_ids)
        or (file_paths is not None and len(file_paths) != entry_count)
    ):
        raise ApplicationConflict("The playlist and its track-ID plan are out of sync")
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
                raise ApplicationConflict("The playlist and its track-ID plan are out of sync")
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


def _mp3_rating(path: Path) -> int:
    try:
        from mutagen import MutagenError
        from mutagen.id3 import ID3
        tags = ID3(path)
    except ImportError:
        return 0
    except (OSError, MutagenError):
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


def parse_crate_tracks(
    path: Path,
    crate_directory: Path,
    *,
    media_reader,
) -> list[dict]:
    path = Path(path)
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as error:
        raise ApplicationError(f"Could not read playlist {path.name}") from error

    plan_path, plan = read_plan_ids(path, lines, crate_directory)
    plan_tracks = []
    if plan is not None:
        try:
            plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
            plan_tracks = plan_data.get("tracks", []) if isinstance(plan_data, dict) else []
        except (OSError, UnicodeError, json.JSONDecodeError):
            plan_tracks = []

    records = []
    for _, plan_index, audio, track_id, rekordbox_id in playlist_entries(path, lines, plan):
        try:
            media = media_reader(audio, easy=True)
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
        records.append({
            "id": track_id,
            "playlist_id": path.stem,
            "rekordbox_id": rekordbox_id,
            "title": plan_text("title", tag("title", audio.stem)),
            "artist": plan_text("artist", tag("artist")),
            "album": plan_text("album", tag("album")),
            "genre": plan_text("genre"),
            "duration": plan_number("duration", round(getattr(info, "length", 0) or 0), integer=True),
            "rating": plan_rating if 0 < plan_rating <= 5 else (
                _mp3_rating(audio) if audio.suffix.lower() == ".mp3" else 0
            ),
            "play_count": plan_number("play_count", 0, integer=True),
            "cue_count": plan_number("cue_count", 0, integer=True),
            "playlist_count": plan_number("playlist_count", len(playlists), integer=True),
            "playlists": playlists,
            "bpm": plan_number("bpm", audio_bpm) or audio_bpm,
            "key": plan_text("key", tag("initialkey")),
            "quality": f"{audio.suffix[1:].upper()} {bitrate // 1000}kbps".strip(),
            "_audio_path": audio,
        })
    return records


def _ensure_app_directories(playlist_directory: Path, crate_directory: Path, default_playlist_directory: Path) -> None:
    if (
        Path(default_playlist_directory).is_symlink()
        or Path(playlist_directory) != Path(default_playlist_directory)
        or Path(crate_directory).is_symlink()
        or Path(crate_directory).parent.is_symlink()
    ):
        raise ApplicationForbidden("Playlist edits are limited to the app's playlist and CrateBox data folders")


def find_crate(playlist_id: str, playlist_directory: Path) -> Path:
    matches = [path for path in playlist_files(playlist_directory) if path.stem == playlist_id]
    if not matches:
        raise ApplicationNotFound("Playlist not found")
    return matches[0]


def create_crate(
    name: str,
    playlist_directory: Path,
    crate_directory: Path,
    default_playlist_directory: Path,
) -> Path:
    name = name.strip()
    if (
        not name or name in (".", "..") or len(name.encode("utf-8")) > 200
        or any(character in name for character in "/\\") or not name.isprintable()
    ):
        raise ApplicationValidationError(
            "Use a playlist name of up to 200 UTF-8 bytes without path separators or control characters."
        )
    _ensure_app_directories(playlist_directory, crate_directory, default_playlist_directory)
    path = Path(playlist_directory) / f"{name}.m3u8"
    plan_path = Path(crate_directory) / f"{name}.json"
    if (
        any(item.stem.casefold() == name.casefold() for item in playlist_files(playlist_directory))
        or plan_path.exists() or plan_path.is_symlink()
    ):
        raise ApplicationConflict("A playlist with this name already exists")

    try:
        Path(crate_directory).mkdir(parents=True, exist_ok=True)
    except OSError:
        raise ApplicationError("Could not create the CrateBox playlist plan directory") from None

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
        raise ApplicationConflict("A playlist with this name already exists") from None
    except OSError as error:
        if playlist_created:
            path.unlink(missing_ok=True)
        if plan_created:
            plan_path.unlink(missing_ok=True)
        raise ApplicationError("Could not create the playlist") from error
    return path


def _read_crate(path: Path, crate_directory: Path):
    try:
        with path.open(encoding="utf-8-sig", newline="") as playlist:
            lines = playlist.readlines()
    except (OSError, UnicodeError) as error:
        raise ApplicationError("Could not read playlist") from error
    plan_path, plan = read_plan_ids(path, lines, crate_directory)
    plan_data = None
    if plan_path.is_file():
        if plan is None or plan_path.is_symlink() or Path(crate_directory).is_symlink() or Path(crate_directory).parent.is_symlink():
            raise ApplicationConflict("The playlist and its track-ID plan are out of sync")
        try:
            plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise ApplicationConflict("The playlist and its track-ID plan are out of sync") from None
    return lines, plan_path, plan, plan_data


def _write_crate_pair(path: Path, original_text: str, updated_text: str, plan_path: Path, plan_data) -> None:
    playlist_updated = False
    try:
        atomic_write(path, updated_text)
        playlist_updated = True
        if plan_data is not None:
            atomic_write(plan_path, json.dumps(plan_data, ensure_ascii=False, indent=2) + "\n")
    except OSError as error:
        if playlist_updated:
            try:
                atomic_write(path, original_text)
            except OSError:
                raise ApplicationError("Playlist and track-ID plan may be out of sync") from None
        raise ApplicationError("Could not update playlist") from error


def remove_crate_tracks(
    playlist_id: str, track_ids: list[str], playlist_directory: Path,
    crate_directory: Path, default_playlist_directory: Path,
) -> dict:
    _ensure_app_directories(playlist_directory, crate_directory, default_playlist_directory)
    if (
        not track_ids or len(track_ids) > 1000
        or any(not isinstance(track_id, str) or not track_id for track_id in track_ids)
        or len(set(track_ids)) != len(track_ids)
    ):
        raise ApplicationValidationError("Select between 1 and 1000 unique tracks")

    path = find_crate(playlist_id, playlist_directory)
    lines, plan_path, plan, plan_data = _read_crate(path, crate_directory)
    entries = {
        track_id: (line_number, plan_index)
        for line_number, plan_index, _, track_id, _ in playlist_entries(path, lines, plan)
    }
    remove_indices, remove_plan_indices = set(), set()
    for track_id in track_ids:
        if track_id not in entries:
            raise ApplicationNotFound("Track not found in playlist")
        line_number, plan_index = entries[track_id]
        remove_indices.add(line_number)
        remove_plan_indices.add(plan_index)
        if line_number and lines[line_number - 1].lstrip().startswith("#EXTINF:"):
            remove_indices.add(line_number - 1)

    updated_lines = [line for index, line in enumerate(lines) if index not in remove_indices]
    if plan_data is not None:
        if isinstance(plan_data.get("tracks"), list):
            plan_data["tracks"] = [
                entry for index, entry in enumerate(plan_data["tracks"])
                if index not in remove_plan_indices
            ]
        else:
            plan_data["track_ids"] = [
                item for index, item in enumerate(plan_data["track_ids"])
                if index not in remove_plan_indices
            ]
    _write_crate_pair(path, "".join(lines), "".join(updated_lines), plan_path, plan_data)
    return {"removed": len(track_ids)}


def replace_crate_track(
    playlist_id: str, source_track_id: str, replacement_track_id: str,
    replacement_audio: Path | None, playlist_directory: Path, crate_directory: Path,
    default_playlist_directory: Path,
) -> dict:
    _ensure_app_directories(playlist_directory, crate_directory, default_playlist_directory)
    if not source_track_id or not replacement_track_id:
        raise ApplicationValidationError("Both playlist and replacement track IDs are required")
    if replacement_audio is None or not Path(replacement_audio).is_file():
        raise ApplicationNotFound("Replacement track is unavailable; run lookup again")
    replacement_audio = Path(replacement_audio)

    path = find_crate(playlist_id, playlist_directory)
    lines, plan_path, plan, plan_data = _read_crate(path, crate_directory)
    entries = list(playlist_entries(path, lines, plan))
    source = next((entry for entry in entries if entry[3] == source_track_id), None)
    if source is None:
        raise ApplicationNotFound("Source track not found in playlist")
    line_number, plan_index = source[0], source[1]
    original_text = "".join(lines)
    line_ending = "\r\n" if lines[line_number].endswith("\r\n") else "\n" if lines[line_number].endswith("\n") else ""
    lines[line_number] = f"{replacement_audio}{line_ending}"

    if plan_data is not None:
        try:
            if isinstance(plan_data.get("tracks"), list):
                plan_item = plan_data["tracks"][plan_index]
                plan_item["track_id"] = replacement_track_id
                plan_item["file_path"] = str(replacement_audio)
                for key in (
                    "title", "artist", "album", "genre", "bpm", "key", "rating",
                    "duration", "bitrate", "sample_rate", "play_count", "cue_count",
                    "playlist_count", "playlists",
                ):
                    plan_item.pop(key, None)
            else:
                plan_data["track_ids"][plan_index] = replacement_track_id
        except (AttributeError, IndexError, KeyError, TypeError):
            raise ApplicationConflict("The playlist and its track-ID plan are out of sync") from None

    _write_crate_pair(path, original_text, "".join(lines), plan_path, plan_data)
    updated_plan = None
    if plan is not None:
        track_ids = list(plan[0])
        track_ids[plan_index] = replacement_track_id
        file_paths = list(plan[1]) if plan[1] is not None else None
        if file_paths is not None:
            file_paths[plan_index] = str(replacement_audio)
        updated_plan = (track_ids, file_paths)
    updated_entries = playlist_entries(path, lines, updated_plan)
    updated_track = next((entry for entry in updated_entries if entry[1] == plan_index), None)
    return {"track_id": updated_track[3] if updated_track else None}


def reorder_crate_tracks(
    playlist_id: str, source_track_ids: list[str], target_track_id: str, before: bool,
    playlist_directory: Path, crate_directory: Path, default_playlist_directory: Path,
) -> dict:
    _ensure_app_directories(playlist_directory, crate_directory, default_playlist_directory)
    if (
        not source_track_ids or len(source_track_ids) > 1000
        or any(not isinstance(track_id, str) or not track_id for track_id in source_track_ids)
        or len(set(source_track_ids)) != len(source_track_ids) or not target_track_id
    ):
        raise ApplicationValidationError("Valid source and target playlist track IDs are required")

    path = find_crate(playlist_id, playlist_directory)
    lines, plan_path, plan, plan_data = _read_crate(path, crate_directory)
    original_entries = list(playlist_entries(path, lines, plan, include_missing=True))
    source_ids = set(source_track_ids)
    source_entries = [entry for entry in original_entries if entry[3] in source_ids]
    target_entry = next((entry for entry in original_entries if entry[3] == target_track_id), None)
    if len(source_entries) != len(source_ids) or target_entry is None:
        raise ApplicationNotFound("Track not found in playlist")
    if target_track_id in source_ids:
        return {"moved": False}
    entries = [entry for entry in original_entries if entry[3] not in source_ids]
    target_index = next(index for index, entry in enumerate(entries) if entry[0] == target_entry[0])
    insertion_index = target_index + (0 if before else 1)
    entries[insertion_index:insertion_index] = source_entries

    first_line = original_entries[0][0]
    if first_line > 0 and lines[first_line - 1].lstrip().startswith("#EXTINF:"):
        first_line -= 1
    header = lines[:first_line]
    blocks, previous_line = [], first_line - 1
    for entry in original_entries:
        line_number = entry[0]
        blocks.append(lines[previous_line + 1:line_number + 1])
        previous_line = line_number
    suffix = lines[previous_line + 1:]
    blocks_by_line = {entry[0]: block for entry, block in zip(original_entries, blocks, strict=True)}
    updated_lines = header + [line for entry in entries for line in blocks_by_line[entry[0]]] + suffix

    if plan_data is not None:
        try:
            order = [entry[1] for entry in entries]
            if isinstance(plan_data.get("tracks"), list):
                plan_data["tracks"] = [plan_data["tracks"][index] for index in order]
            else:
                plan_data["track_ids"] = [plan_data["track_ids"][index] for index in order]
        except (AttributeError, IndexError, KeyError, TypeError):
            raise ApplicationConflict("The playlist and its track-ID plan are out of sync") from None
    _write_crate_pair(path, "".join(lines), "".join(updated_lines), plan_path, plan_data)
    return {"moved": True}


def atomic_write(path: Path, content: str) -> None:
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="", dir=path.parent, delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
        temporary_path.chmod(path.stat().st_mode)
        os.replace(temporary_path, path)
    except OSError:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
        raise
