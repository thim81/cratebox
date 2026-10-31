import hashlib
import json
from pathlib import Path

import pytest

from rekordbx_mcp.snapshot import create_snapshot, verify_snapshot


def test_copies_source_without_modifying_or_linking_it(tmp_path, monkeypatch):
    monkeypatch.setattr("rekordbx_mcp.snapshot.require_rekordbox_closed", lambda: None)
    source = tmp_path / "original" / "master.db"
    source.parent.mkdir()
    source.write_bytes(b"fixture collection")
    before = source.stat()
    snapshot = create_snapshot(source, tmp_path / "snapshots")
    assert (snapshot / "master.db").read_bytes() == b"fixture collection"
    assert (snapshot / "master.db").stat().st_ino != before.st_ino
    assert source.stat().st_mtime_ns == before.st_mtime_ns
    assert source.stat().st_mode == before.st_mode
    assert verify_snapshot(snapshot) == snapshot / "master.db"


@pytest.mark.parametrize("sidecar", ["-wal", "-shm", "-journal"])
def test_refuses_source_with_transaction_sidecar(tmp_path, monkeypatch, sidecar):
    monkeypatch.setattr("rekordbx_mcp.snapshot.require_rekordbox_closed", lambda: None)
    source = tmp_path / "master.db"
    source.write_bytes(b"fixture")
    source.with_name(source.name + sidecar).write_bytes(b"pending data")
    with pytest.raises(ValueError, match="sidecar"):
        create_snapshot(source, tmp_path / "snapshots")
    assert not (tmp_path / "snapshots").exists()


def test_refuses_destination_inside_original_directory(tmp_path, monkeypatch):
    monkeypatch.setattr("rekordbx_mcp.snapshot.require_rekordbox_closed", lambda: None)
    source = tmp_path / "master.db"
    source.write_bytes(b"fixture")
    with pytest.raises(ValueError, match="source directory"):
        create_snapshot(source, tmp_path / "snapshots")


def test_tampered_snapshot_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr("rekordbx_mcp.snapshot.require_rekordbox_closed", lambda: None)
    source = tmp_path / "original" / "master.db"
    source.parent.mkdir()
    source.write_bytes(b"fixture")
    snapshot = create_snapshot(source, tmp_path / "snapshots")
    db = snapshot / "master.db"
    db.chmod(0o600)
    db.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash"):
        verify_snapshot(snapshot)


def test_refuses_symlink_as_snapshot_database(tmp_path):
    original = tmp_path / "original.db"
    original.write_bytes(b"fixture")
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "master.db").symlink_to(original)
    (snapshot / "manifest.json").write_text(json.dumps({
        "sha256": hashlib.sha256(b"fixture").hexdigest(),
        "format": 1,
    }))
    with pytest.raises(ValueError, match="symlink"):
        verify_snapshot(snapshot)
