"""Resolve generic collection tracks and write safe CrateBox playlist artifacts."""

import json
import asyncio
import os
import re
import stat
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
STATE_DIRECTORY = REPOSITORY_ROOT / ".cratebox"
CRATE_DIRECTORY = STATE_DIRECTORY / "crates"
PLAYLISTS_DIRECTORY = REPOSITORY_ROOT / "playlists"
SEPARATOR_DIRECTORY = Path("/Users/thim/Library/CloudStorage/OneDrive-Personal/Music/iTunes 2022-03")
SEPARATOR_FILES = {
    "generic": "Separator.wav", "90s": "Separator-90.wav", "R&B": "Separator-RB.wav",
    "Ambi": "Separator-Ambi.wav", "Salsa": "Separator-Salsa.wav",
    "Party": "Separator-Party.wav", "Dance": "Separator-Dance.wav",
}
_UNSAFE_PATH_CHARACTERS = "\r\n\x00\x85\u2028\u2029"


def _validate_name(name: str) -> str:
    name = name.strip()
    if (
        not name or name in (".", "..") or len(name.encode("utf-8")) > 200
        or any(character in name for character in "/\\") or not name.isprintable()
    ):
        raise ValueError("Use a playlist name of up to 200 UTF-8 bytes without path separators or control characters.")
    return name


def _validate_rows(rows: list[dict], expected_ids: list[str] | None = None) -> list[dict]:
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError("The selection must resolve to active collection tracks.")
    if expected_ids is not None and [str(row.get("id") or "") for row in rows] != expected_ids:
        raise ValueError("The selection must resolve to active collection tracks in the requested order.")
    if len(rows) > 1000:
        raise ValueError("Select up to 1000 tracks and separators combined.")
    for position, row in enumerate(rows, 1):
        raw_path = row.get("file_path")
        if (
            not isinstance(row.get("id"), str) or not row["id"]
            or not isinstance(raw_path, str) or not Path(raw_path).is_absolute()
            or any(character in raw_path for character in _UNSAFE_PATH_CHARACTERS)
        ):
            raise ValueError(f"Track at position {position} is unavailable in the active collection.")
        try:
            present = Path(raw_path).is_file()
        except OSError:
            present = False
        if not present:
            raise ValueError(f"Audio for collection track {row['id']} is missing.")
    return rows


def _plan_track(row: dict, separator_type: str | None = None) -> dict:
    playlists = row.get("playlists") or []
    item = {
        "track_id": str(row["id"]),
        "file_path": row["file_path"],
        "title": str(row.get("title") or ""),
        "artist": str(row.get("artist") or ""),
        "album": str(row.get("album") or "") or None,
        "genre": str(row.get("genre") or "") or None,
        "bpm": float(row.get("bpm") or 0),
        "key": str(row.get("key") or "") or None,
        "rating": int(row.get("rating") or 0),
        "duration": int(row.get("duration") or row.get("length") or 0),
        "bitrate": int(row.get("bitrate") or 0) or None,
        "sample_rate": int(row.get("sample_rate") or 0) or None,
        "play_count": int(row.get("play_count") or 0),
        "cue_count": int(row.get("cue_count") or 0),
        "playlist_count": int(row.get("playlist_count") or len(playlists)),
        "playlists": [
            {"id": str(item.get("id") or ""), "name": str(item.get("name") or "")}
            for item in playlists if isinstance(item, dict)
        ],
    }
    if separator_type is not None:
        item["separator_type"] = separator_type
    return item


def _write_pair(
    name: str, playlist_items: list[dict], crate_directory: Path,
    playlists_directory: Path, *, update_existing: bool,
) -> str:
    crate_directory = Path(crate_directory).absolute()
    playlists_directory = Path(playlists_directory).absolute()
    if (
        crate_directory.is_symlink() or crate_directory.parent.is_symlink()
        or playlists_directory.is_symlink()
    ):
        raise ValueError("Export directories must not be symlinks.")
    crate_directory.mkdir(parents=True, exist_ok=True)
    playlists_directory.mkdir(exist_ok=True)
    plan_fd = os.open(crate_directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        playlists_fd = os.open(playlists_directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except BaseException:
        os.close(plan_fd)
        raise
    try:
        old_pattern = re.compile(rf"{re.escape(name)}-v(\d+)")
        plan_names, playlist_names = set(os.listdir(plan_fd)), set(os.listdir(playlists_fd))
        existing_names = {
            Path(filename).stem for filename in plan_names | playlist_names
            if Path(filename).suffix in (".m3u8", ".json")
            and (Path(filename).stem == name or old_pattern.fullmatch(Path(filename).stem))
        }
        if existing_names and not update_existing:
            existing_name = name if name in existing_names else max(
                existing_names, key=lambda item: int(old_pattern.fullmatch(item).group(1)),
            )
            raise FileExistsError(
                f"An export named {existing_name!r} already exists. Ask whether to update that playlist "
                "or create a separate playlist with a different name. If updating, call again with "
                "update_existing=true."
            )
        if update_existing and not existing_names:
            raise ValueError("Cannot update this playlist because no earlier local export was found.")
        target_name = name if name in existing_names else (
            max(existing_names, key=lambda item: int(old_pattern.fullmatch(item).group(1)))
            if update_existing else name
        )
        plan = {
            "format": 1, "name": target_name, "tracks": playlist_items,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        artifacts = [
            (playlists_fd, f"{target_name}.m3u8", "#EXTM3U\n" + "\n".join(
                item["file_path"] for item in playlist_items
            ) + "\n"),
            (plan_fd, f"{target_name}.json", json.dumps(plan, ensure_ascii=False, indent=2) + "\n"),
        ]
        if update_existing:
            backups, temporaries, installed = [], [], []
            try:
                for directory_fd, filename, _ in artifacts:
                    try:
                        current = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    if not stat.S_ISREG(current.st_mode):
                        raise ValueError("Cannot update an export containing a symlink or non-file artifact.")
                    backup = f".{filename}.{uuid4().hex}.bak"
                    os.link(filename, backup, src_dir_fd=directory_fd, dst_dir_fd=directory_fd, follow_symlinks=False)
                    backups.append((directory_fd, backup, filename))
                for directory_fd, filename, content in artifacts:
                    temporary = f".{filename}.{uuid4().hex}.tmp"
                    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
                    temporaries.append((directory_fd, temporary))
                    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                        stream.write(content)
                        stream.flush()
                        os.fsync(stream.fileno())
                for (directory_fd, filename, _), (_, temporary) in zip(artifacts, temporaries, strict=True):
                    os.replace(temporary, filename, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
                    installed.append((directory_fd, filename))
                    temporaries = [item for item in temporaries if item[1] != temporary]
            except BaseException:
                backed_up = {(directory_fd, filename) for directory_fd, _, filename in backups}
                for directory_fd, filename in reversed(installed):
                    if (directory_fd, filename) not in backed_up:
                        try: os.unlink(filename, dir_fd=directory_fd)
                        except OSError: pass
                for directory_fd, backup, filename in reversed(backups):
                    try:
                        os.replace(backup, filename, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
                        os.unlink(backup, dir_fd=directory_fd)
                    except OSError: pass
                for directory_fd, temporary in temporaries:
                    try: os.unlink(temporary, dir_fd=directory_fd)
                    except OSError: pass
                raise
            for directory_fd, backup, _ in backups:
                try: os.unlink(backup, dir_fd=directory_fd)
                except OSError: pass
        else:
            created = []
            try:
                for directory_fd, filename, content in artifacts:
                    fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
                    created.append((directory_fd, filename))
                    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                        stream.write(content)
                        stream.flush()
                        os.fsync(stream.fileno())
            except BaseException:
                for directory_fd, filename in created:
                    try: os.unlink(filename, dir_fd=directory_fd)
                    except OSError: pass
                raise
        return target_name
    finally:
        os.close(playlists_fd)
        os.close(plan_fd)


async def export_playlist(
    name: str,
    *,
    track_ids: list[str] | None,
    file_paths: list[str] | None,
    resolve_tracks: Callable[..., Awaitable[list[dict]]],
    crate_directory: Path = CRATE_DIRECTORY,
    playlists_directory: Path = PLAYLISTS_DIRECTORY,
    update_existing: bool = False,
    separators: list[dict] | None = None,
) -> dict:
    name = _validate_name(name)
    if (track_ids is None) == (file_paths is None):
        raise ValueError("Supply exactly one of track_ids or file_paths.")
    if track_ids is not None and (
        not track_ids or len(track_ids) > 1000 or any(
            not isinstance(item, str) or not item or not item.isprintable()
            or "/" in item or "\\" in item for item in track_ids
        )
    ):
        raise ValueError("Select 1–1000 nonempty string track IDs.")
    if file_paths is not None and (
        not file_paths or len(file_paths) > 1000 or any(
            not isinstance(path, str) or not Path(path).is_absolute()
            or any(character in path for character in _UNSAFE_PATH_CHARACTERS)
            for path in file_paths
        )
    ):
        raise ValueError("Select 1–1000 absolute file locations.")

    selector = {"track_ids": track_ids} if track_ids is not None else {"file_paths": file_paths}
    rows = _validate_rows(await resolve_tracks(**selector), track_ids)
    if file_paths is not None and [row.get("file_path") for row in rows] != file_paths:
        raise ValueError("Each file location must match exactly one active collection track.")
    separators = separators or []
    if not isinstance(separators, list) or len(rows) + len(separators) > 1000:
        raise ValueError("Select up to 1000 tracks and separators combined.")
    separators_before: dict[int, list[tuple[dict, str]]] = {}
    for index, separator in enumerate(separators, 1):
        if not isinstance(separator, dict) or set(separator) != {"type", "before_track"}:
            raise ValueError(f"Invalid separator at position {index}; provide only type and before_track.")
        kind, before = separator["type"], separator["before_track"]
        if not isinstance(kind, str) or kind not in SEPARATOR_FILES:
            raise ValueError(f"Invalid separator type at position {index}.")
        if not isinstance(before, int) or isinstance(before, bool) or not 1 <= before <= len(rows) + 1:
            raise ValueError(f"Invalid before_track at separator position {index}.")
        separator_path = SEPARATOR_DIRECTORY / SEPARATOR_FILES[kind]
        if not separator_path.is_file():
            raise ValueError(f"Separator {kind!r} is unavailable in the configured music folder.")
        resolved = _validate_rows(await resolve_tracks(file_paths=[str(separator_path)]))
        if len(resolved) != 1 or resolved[0]["file_path"] != str(separator_path):
            raise ValueError(f"Separator {kind!r} must match exactly one active collection track.")
        separators_before.setdefault(before, []).append((resolved[0], kind))

    playlist_items = []
    for position in range(1, len(rows) + 2):
        playlist_items.extend(_plan_track(item, kind) for item, kind in separators_before.get(position, []))
        if position <= len(rows):
            playlist_items.append(_plan_track(rows[position - 1]))
    target_name = await asyncio.to_thread(
        _write_pair, name, playlist_items, crate_directory, playlists_directory,
        update_existing=update_existing,
    )
    return {
        "playlist_path": str(Path(playlists_directory) / f"{target_name}.m3u8"),
        "plan_path": str(Path(crate_directory) / f"{target_name}.json"),
        "name": target_name,
        "updated_existing": update_existing,
        "track_count": len(rows),
        "separator_count": len(separators),
    }
