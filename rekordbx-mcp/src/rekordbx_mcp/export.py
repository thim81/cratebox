"""Create external playlist artifacts; never write to collection or audio files."""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .database import SnapshotMasterDatabase


OUTPUT_DIRECTORY = Path(__file__).resolve().parents[3] / "output"
PLAYLISTS_DIRECTORY = Path(__file__).resolve().parents[3] / "playlists"


def export_playlist(
    database: SnapshotMasterDatabase,
    name: str,
    track_ids: list[str] | None,
    output_directory: Path,
    *,
    file_paths: list[str] | None = None,
    playlists_directory: Path | None = None,
    revision: bool = False,
) -> dict:
    name = name.strip()
    if (
        not name or name in (".", "..") or len(name.encode("utf-8")) > 200
        or any(character in name for character in "/\\") or not name.isprintable()
    ):
        raise ValueError("Use a playlist name of up to 200 UTF-8 bytes without path separators or control characters.")
    if (track_ids is None) == (file_paths is None):
        raise ValueError("Supply exactly one of track_ids or file_paths.")
    if file_paths is not None:
        if not file_paths or len(file_paths) > 1000:
            raise ValueError("Select 1–1000 file locations.")
        track_ids = []
        for position, location in enumerate(file_paths, 1):
            if (
                not isinstance(location, str) or not Path(location).is_absolute()
                or any(character in location for character in "\r\n\x00\x85\u2028\u2029")
            ):
                raise ValueError(f"Invalid file location at position {position}; use an absolute local path.")
            matches = [
                track for track in database.get_content().filter_by(FolderPath=location)
                if not track.rb_local_deleted
            ]
            if len(matches) != 1:
                raise ValueError(f"File location at position {position} must match exactly one active snapshot track.")
            track_ids.append(str(matches[0].ID))
    if not track_ids:
        raise ValueError("Select at least one track ID.")
    if len(track_ids) > 1000 or any(
        not isinstance(item, str) or not item or not item.isprintable()
        or "/" in item or "\\" in item for item in track_ids
    ):
        raise ValueError("Select up to 1000 nonempty string track IDs.")

    paths = []
    unknown, missing, unsafe = [], [], []
    for track_id in track_ids:
        track = database.get_content(ID=track_id)
        if track is None or track.rb_local_deleted:
            unknown.append(track_id)
            continue
        raw = track.FolderPath or ""
        if not Path(raw).is_absolute() or any(
            character in raw for character in "\r\n\x00\x85\u2028\u2029"
        ):
            unsafe.append(track_id)
            continue
        try:
            exists = Path(raw).is_file()
        except OSError:
            exists = False
        if not exists:
            missing.append(track_id)
        paths.append(raw)
    problems = []
    for label, ids in (
        ("unknown/deleted track IDs", unknown), ("missing audio for track IDs", missing),
        ("invalid audio paths for track IDs", unsafe),
    ):
        if ids:
            problems.append(f"{label}: {', '.join(dict.fromkeys(ids))}")
    if problems:
        raise ValueError("Cannot export; " + "; ".join(problems))

    output_directory = Path(output_directory).absolute()
    playlists_directory = Path(
        playlists_directory if playlists_directory is not None else Path(output_directory).parent / "playlists"
    ).absolute()
    if output_directory.is_symlink() or playlists_directory.is_symlink():
        raise ValueError("Export directories must not be symlinks.")
    output_directory.mkdir(exist_ok=True)
    playlists_directory.mkdir(exist_ok=True)

    output_fd = os.open(output_directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        playlists_fd = os.open(playlists_directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except BaseException:
        os.close(output_fd)
        raise
    try:
        revision_pattern = re.compile(rf"{re.escape(name)}-v(\d+)\.(?:m3u8|json)")

        def existing_revision_numbers():
            output_names = set(os.listdir(output_fd))
            playlist_names = set(os.listdir(playlists_fd))
            numbers = [
                int(match.group(1))
                for filename in output_names | playlist_names
                if (match := revision_pattern.fullmatch(filename))
            ]
            legacy = (
                f"{name}.json" in output_names
                or f"{name}.m3u8" in output_names
                or f"{name}.m3u8" in playlist_names
            )
            return numbers, legacy

        existing_revisions, has_legacy_export = existing_revision_numbers()
        has_existing_export = bool(existing_revisions) or has_legacy_export
        if has_existing_export and not revision:
            raise FileExistsError(
                f"An export named {name!r} already exists. Ask whether to create its next numbered revision "
                "or start a separate playlist with a new name. If revising, call again with revision=true."
            )
        if revision and not has_existing_export:
            raise ValueError("Cannot revise this playlist because no earlier local export was found.")
    except BaseException:
        os.close(playlists_fd)
        os.close(output_fd)
        raise

    try:
        for attempt in range(8):
            existing_revisions, has_legacy_export = existing_revision_numbers()
            if not revision and (existing_revisions or has_legacy_export):
                raise FileExistsError(
                    f"An export named {name!r} already exists. Ask whether to create its next numbered revision "
                    "or start a separate playlist with a new name. If revising, call again with revision=true."
                )
            revision_name = f"{name}-v{max(existing_revisions, default=0) + 1:03d}"
            plan = {
                "format": 1, "name": revision_name, "revision_of": name,
                "tracks": [
                    {"track_id": track_id, "file_path": path}
                    for track_id, path in zip(track_ids, paths, strict=True)
                ],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            artifacts = [
                (playlists_fd, f"{revision_name}.m3u8", "#EXTM3U\n" + "\n".join(paths) + "\n"),
                (output_fd, f"{revision_name}.json", json.dumps(plan, ensure_ascii=False, indent=2) + "\n"),
            ]
            created = []
            try:
                for directory_fd, filename, content in artifacts:
                    fd = os.open(
                        filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600, dir_fd=directory_fd,
                    )
                    created.append((directory_fd, filename))
                    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                        stream.write(content)
                        stream.flush()
                        os.fsync(stream.fileno())
            except FileExistsError:
                for directory_fd, filename in created:
                    try:
                        os.unlink(filename, dir_fd=directory_fd)
                    except OSError:
                        pass
                if not revision:
                    raise FileExistsError(
                        f"An export named {name!r} already exists. Ask whether to create its next numbered revision "
                        "or start a separate playlist with a new name. If revising, call again with revision=true."
                    ) from None
                if attempt == 7:
                    raise FileExistsError("Could not reserve a revision after repeated concurrent exports.") from None
            except BaseException:
                for directory_fd, filename in created:
                    try:
                        os.unlink(filename, dir_fd=directory_fd)
                    except OSError:
                        pass
                raise
            else:
                break
    finally:
        os.close(playlists_fd)
        os.close(output_fd)
    return {
        "playlist_path": str(playlists_directory / f"{revision_name}.m3u8"),
        "plan_path": str(output_directory / f"{revision_name}.json"),
        "revision_name": revision_name,
        "track_count": len(track_ids),
    }
