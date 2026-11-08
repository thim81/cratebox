"""Opaque playlist revisions for detecting local and external edits."""

import hashlib
import secrets
import threading
from pathlib import Path


class PlaylistRevision:
    def __init__(self, playlist_directory: Path, plan_directory: Path):
        self.playlist_directory = Path(playlist_directory)
        self.plan_directory = Path(plan_directory)
        self._process_nonce = secrets.token_bytes(32)
        self._successful_writes = 0
        self._lock = threading.Lock()

    def mark_written(self) -> None:
        with self._lock:
            self._successful_writes += 1

    def value(self) -> str:
        digest = hashlib.sha256(self._process_nonce)
        with self._lock:
            digest.update(str(self._successful_writes).encode())
        for directory, suffixes in (
            (self.playlist_directory, {".m3u", ".m3u8"}),
            (self.plan_directory, {".json"}),
        ):
            try:
                files = sorted(directory.iterdir(), key=lambda item: item.name.casefold())
            except OSError:
                files = []
            for path in files:
                if path.suffix.lower() not in suffixes or path.is_symlink() or not path.is_file():
                    continue
                if path.suffix.lower() == ".json" and not any(
                    (self.playlist_directory / f"{path.stem}{suffix}").is_file()
                    for suffix in (".m3u", ".m3u8")
                ):
                    continue
                try:
                    digest.update(path.name.encode("utf-8", errors="replace"))
                    with path.open("rb") as stream:
                        for chunk in iter(lambda: stream.read(64 * 1024), b""):
                            digest.update(chunk)
                except OSError:
                    digest.update(b"unreadable")
        return digest.hexdigest()
