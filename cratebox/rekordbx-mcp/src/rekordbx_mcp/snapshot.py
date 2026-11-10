"""Copy bytes from a closed Rekordbox collection; never open its database."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import psutil


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def rekordbox_is_running() -> bool:
    # An unreadable process list must fail closed, not imply Rekordbox is closed.
    try:
        for process in psutil.process_iter(["name"]):
            name = process.info["name"]
            if name is None:
                raise RuntimeError("Cannot verify Rekordbox is closed: unreadable process name.")
            if "rekordbox" in name.lower():
                return True
    except (psutil.Error, OSError) as error:
        raise RuntimeError("Cannot verify Rekordbox is closed: process inspection failed.") from error
    return False


def require_rekordbox_closed() -> None:
    if rekordbox_is_running():
        raise RuntimeError("Close Rekordbox and its background agents to access the collection.")


def latest_snapshot(destination: Path) -> Path:
    destination = Path(destination).resolve()
    snapshots = sorted(
        (child for child in destination.iterdir()
         if child.is_dir() and not child.is_symlink()
         and len(child.name) == 32 and all(c in "0123456789abcdef" for c in child.name)),
        key=lambda child: child.stat().st_mtime_ns,
        reverse=True,
    ) if destination.is_dir() else []
    if not snapshots:
        raise RuntimeError(
            "Rekordbox is running and no snapshot exists; close Rekordbox and run "
            "'rekordbx-mcp snapshot' first."
        )
    snapshot = snapshots[0]
    try:
        verify_snapshot(snapshot)
    except (OSError, ValueError, RuntimeError) as error:
        raise RuntimeError("The newest Rekordbox snapshot is invalid; create a fresh snapshot with Rekordbox closed.") from error
    return snapshot


def reject_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        if path.with_name(path.name + suffix).exists():
            raise ValueError("Database transaction sidecar exists; close Rekordbox cleanly.")


def create_snapshot(source: Path, destination: Path) -> Path:
    source = Path(source).absolute()
    if source.is_symlink():
        raise ValueError("Source database must not be a symlink.")
    source = source.resolve(strict=True)
    require_rekordbox_closed()
    reject_sidecars(source)
    destination = Path(destination).resolve()
    if destination.is_relative_to(source.parent):
        raise ValueError("Snapshot destination must be outside the source directory.")
    before = source.stat()
    digest = sha256(source)
    destination.mkdir(parents=True, exist_ok=True)
    snapshot = destination / uuid4().hex
    snapshot.mkdir(mode=0o700)
    target = snapshot / "master.db"
    # Explicit new file, no links and no metadata operations on the source.
    with source.open("rb") as reader, target.open("xb") as writer:
        import shutil
        shutil.copyfileobj(reader, writer)
        writer.flush()
        os.fsync(writer.fileno())
    require_rekordbox_closed()
    reject_sidecars(source)
    after = source.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_ino, after.st_size, after.st_mtime_ns
    ) or sha256(source) != digest or sha256(target) != digest:
        raise RuntimeError("Source changed during copying; snapshot is not usable.")
    manifest = {
        "format": 1,
        "sha256": digest,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (snapshot / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    target.chmod(0o400)
    return snapshot


def verify_snapshot(snapshot: Path) -> Path:
    snapshot = Path(snapshot).absolute()
    if snapshot.is_symlink():
        raise ValueError("Snapshot directory must not be a symlink.")
    database = snapshot / "master.db"
    if database.is_symlink() or (snapshot / "manifest.json").is_symlink():
        raise ValueError("Snapshot files must not be symlinks.")
    if database.stat().st_nlink != 1:
        raise ValueError("Snapshot database must not be a hard link.")
    reject_sidecars(database)
    manifest = json.loads((snapshot / "manifest.json").read_text())
    if manifest.get("format") != 1 or sha256(database) != manifest.get("sha256"):
        raise ValueError("Snapshot hash or manifest is invalid.")
    return database.resolve(strict=True)
