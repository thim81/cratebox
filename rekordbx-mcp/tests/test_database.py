import pytest

from rekordbx_mcp.database import open_readonly_connection


def test_encrypted_connection_reads_but_rejects_writes(encrypted_database):
    with open_readonly_connection(encrypted_database) as conn:
        assert conn.execute("SELECT Title FROM djmdContent").fetchone()[0] == "One More Time"
        with pytest.raises(Exception):
            conn.execute("UPDATE djmdContent SET Title='changed'")
        with pytest.raises(Exception):
            conn.execute("PRAGMA query_only=OFF")
        with pytest.raises(Exception):
            conn.execute("ATTACH DATABASE ':memory:' AS extra")
        assert conn.execute("SELECT Title FROM djmdContent").fetchone()[0] == "One More Time"


def test_missing_database_is_never_created(tmp_path):
    missing = tmp_path / "master.db"
    with pytest.raises(FileNotFoundError):
        open_readonly_connection(missing)
    assert not missing.exists()
