import pytest
from sqlalchemy.exc import DatabaseError
from sqlcipher3 import dbapi2 as sqlite

from rekordbx_mcp.database import SnapshotMasterDatabase, open_readonly_connection


def test_encrypted_connection_reads_but_rejects_writes(encrypted_database):
    with open_readonly_connection(encrypted_database) as conn:
        assert conn.execute("SELECT Title FROM djmdContent").fetchone()[0] == "One More Time"
        with pytest.raises(sqlite.DatabaseError):
            conn.execute("UPDATE djmdContent SET Title='changed'")
        with pytest.raises(sqlite.DatabaseError):
            conn.execute("PRAGMA query_only=OFF")
        with pytest.raises(sqlite.DatabaseError):
            conn.execute("ATTACH DATABASE ':memory:' AS extra")
        assert conn.execute("SELECT Title FROM djmdContent").fetchone()[0] == "One More Time"


def test_missing_database_is_never_created(tmp_path):
    missing = tmp_path / "master.db"
    with pytest.raises(FileNotFoundError):
        open_readonly_connection(missing)
    assert not missing.exists()


def test_orm_commit_and_flush_cannot_modify_snapshot(encrypted_database):
    from rekordbx_mcp.snapshot import sha256
    before = sha256(encrypted_database)
    database = SnapshotMasterDatabase(encrypted_database)
    try:
        track = database.get_content(ID="1")
        track.Title = "Forbidden change"
        with pytest.raises(PermissionError, match="read-only"):
            database.commit()
        with pytest.raises(DatabaseError):
            database.session.flush()
        database.session.rollback()
        assert database.get_content(ID="1").Title == "One More Time"
    finally:
        database.close()
    assert sha256(encrypted_database) == before
