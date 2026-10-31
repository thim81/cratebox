"""Create external playlist artifacts; never write to collection or audio files."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .database import SnapshotMasterDatabase


OUTPUT_DIRECTORY = Path(__file__).resolve().parents[3] / "output"


def export_playlist(
    database: SnapshotMasterDatabase,
    name: str,
    track_ids: list[str] | None,
    output_directory: Path,
    *,
    file_paths: list[str] | None = None,
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
    if len(track_ids) > 1000 or any(not isinstance(item, str) or not item for item in track_ids):
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
    if output_directory.is_symlink():
        raise ValueError("Export directory must not be a symlink.")
    output_directory.mkdir(exist_ok=True)
    plan = {
        "format": 1, "name": name, "track_ids": track_ids,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    artifacts = {
        f"{name}.m3u8": "#EXTM3U\n" + "\n".join(paths) + "\n",
        f"{name}.json": json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
    }
    # Pin the directory descriptor and create exclusively: never follow an
    # output symlink or overwrite an existing file, including on retries.
    directory_fd = os.open(output_directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    created = []
    try:
        for filename, content in artifacts.items():
            fd = os.open(
                filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=directory_fd,
            )
            created.append(filename)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
    except BaseException:
        for filename in created:
            os.unlink(filename, dir_fd=directory_fd)
        raise
    finally:
        os.close(directory_fd)
    return {
        "playlist_path": str(output_directory / f"{name}.m3u8"),
        "plan_path": str(output_directory / f"{name}.json"),
        "track_count": len(track_ids),
    }
