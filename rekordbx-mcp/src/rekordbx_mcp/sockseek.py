"""Write Sockseek list inputs without running the downloader."""

import json
import os
import shlex
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SOCKSEEK_EXECUTABLE = REPOSITORY_ROOT / "sockseek" / "sockseek"


def _open_directory_tree(directory: Path) -> int:
    if not directory.is_absolute():
        raise ValueError("Sockseek output directory must be absolute.")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in directory.parts[1:]:
            if component in ("", ".", ".."):
                raise ValueError("Sockseek output directory contains an unsafe path component.")
            try:
                os.mkdir(component, mode=0o700, dir_fd=fd)
            except FileExistsError:
                pass
            next_fd = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd,
            )
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def create_sockseek_list(name: str, tracks: list[dict]) -> dict:
    name = name.strip()
    if (
        not name or name in (".", "..") or len(name.encode("utf-8")) > 160
        or any(character in name for character in "/\\") or not name.isprintable()
    ):
        raise ValueError("Use a printable list name of up to 160 UTF-8 bytes without path separators.")
    if not tracks or len(tracks) > 1000:
        raise ValueError("Provide between 1 and 1000 tracks.")

    rows = []
    for position, track in enumerate(tracks, 1):
        if not isinstance(track, dict):
            raise ValueError(f"Track {position} must include artist and title.")
        artist = track.get("artist")
        title = track.get("title")
        if not isinstance(artist, str) or not isinstance(title, str):
            raise ValueError(f"Track {position} must include artist and title.")
        artist, title = artist.strip(), title.strip()
        if (
            not artist or not title or len(artist) > 500 or len(title) > 1000
            or not artist.isprintable() or not title.isprintable()
        ):
            raise ValueError(f"Track {position} has an empty artist/title or contains control characters.")
        rows.append("s:" + json.dumps(f"{artist} - {title}", ensure_ascii=False))

    list_directory = REPOSITORY_ROOT / "output" / "sockseek-lists"
    download_directory = Path.home() / "Downloads" / "Soulseek" / name
    directory_fd = _open_directory_tree(list_directory)
    filename = f"{name} - Missing Tracks.txt"
    try:
        fd = os.open(
            filename,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write("\n".join(rows) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            try:
                os.unlink(filename, dir_fd=directory_fd)
            except OSError:
                pass
            raise
    finally:
        os.close(directory_fd)

    list_path = list_directory / filename
    playlist_path = download_directory / f"{name}.m3u8"
    log_path = download_directory / f"{name}.sockseek.log"
    relative_executable = f"./{SOCKSEEK_EXECUTABLE.relative_to(REPOSITORY_ROOT).as_posix()}"
    relative_list_path = list_path.relative_to(REPOSITORY_ROOT).as_posix()
    command_groups = [
        (relative_executable,), (relative_list_path,), ("--input-type=list",),
        ("--output-dir", str(download_directory)),
        ("--name-format", "{artist( - )title|filename}"),
        ("--write-playlist",), ("--playlist-path", str(playlist_path)),
        ("--skip-mode-output-dir", "name"), ("--format", "mp3"),
        ("--no-listen",), ("--log-file", str(log_path)),
        ("--min-bitrate", "128"), ("--pref-min-bitrate", "320"),
        ("--concurrent-jobs", "4"), ("--concurrent-searches", "1"),
    ]
    command = shlex.quote(command_groups[0][0]) + " \\\n" + " \\\n".join(
        "  " + " ".join(shlex.quote(argument) for argument in group)
        for group in command_groups[1:]
    )
    return {
        "name": name,
        "track_count": len(rows),
        "list_path": str(list_path),
        "run_from": str(REPOSITORY_ROOT),
        "download_directory": str(download_directory),
        "playlist_path": str(playlist_path),
        "log_path": str(log_path),
        "command": command,
    }
