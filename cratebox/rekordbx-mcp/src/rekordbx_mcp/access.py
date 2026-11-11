"""Shared checks for Rekordbox database access and recovery."""

import hashlib
from pathlib import Path

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


def reject_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        if path.with_name(path.name + suffix).exists() or path.with_name(path.name + suffix).is_symlink():
            raise ValueError("Database transaction sidecar exists; close Rekordbox cleanly.")


def reject_rollback_journal(path: Path) -> None:
    """Normal WAL files are handled by SQLite; never open a pending rollback journal."""
    for suffix in ('-wal', '-shm', '-journal'):
        sidecar = path.with_name(path.name + suffix)
        if sidecar.is_symlink() or (suffix == '-journal' and sidecar.exists()):
            raise ValueError('Database transaction sidecar exists; close Rekordbox cleanly.')
    wal = path.with_name(path.name + '-wal')
    if wal.exists() and wal.stat().st_size:
        with wal.open('rb') as stream:
            magic = stream.read(4)
        if magic not in (b'\x37\x7f\x06\x82', b'\x37\x7f\x06\x83'):
            raise ValueError('Unrecognized database WAL sidecar; close Rekordbox cleanly.')
