from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def closed_processes(monkeypatch):
    monkeypatch.setattr("rekordbx_mcp.snapshot.psutil.process_iter", lambda *_: [])


@pytest.fixture
def encrypted_database(encrypted_database, tmp_path):
    target = tmp_path / "original" / "master.db"
    target.parent.mkdir()
    encrypted_database.rename(target)
    return target


def manager(source, directory):
    from rekordbx_mcp import backup
    assert hasattr(backup, 'BackupManager')
    return backup.BackupManager(source, directory)


def test_backup_cooldown_and_real_encrypted_restore(encrypted_database, tmp_path, monkeypatch):
    import rekordbx_mcp.backup as backup
    clock = [1000.0]
    monkeypatch.setattr(backup.time, 'monotonic', lambda: clock[0])
    storage = tmp_path / 'backups'
    xml = encrypted_database.with_name('masterPlaylists6.xml')
    xml.write_text('<PLAYLISTS/>')
    m = manager(encrypted_database, storage)
    with m.lock():
        first = m.ensure()
        assert m.ensure() == first
        clock[0] += 300
        second = m.ensure()
        assert second != first
    before = encrypted_database.read_bytes()
    encrypted_database.write_bytes(b'damaged')
    xml.write_text('<changed/>')
    # Recovery must not require the damaged current database to pass integrity checks.
    m.restore(first.name)
    assert encrypted_database.read_bytes() == before
    assert xml.read_text() == '<PLAYLISTS/>'
    assert len(m.list()) == 3  # includes the preserved pre-restore files
    assert encrypted_database.parent != first.parent


def test_corrupted_reused_backup_blocks_write(encrypted_database, tmp_path):
    m = manager(encrypted_database, tmp_path / 'backups')
    with m.lock():
        point = m.ensure()
        (point / 'master.db').write_bytes(b'bad')
        with pytest.raises((ValueError, RuntimeError), match='backup|Backup'):
            m.ensure()


def test_backup_rejects_journals_and_session_always_starts_fresh(encrypted_database, tmp_path):
    m = manager(encrypted_database, tmp_path / 'backups')
    first = m.ensure()
    assert manager(encrypted_database, tmp_path / 'backups').ensure() != first
    encrypted_database.with_name('master.db-wal').write_bytes(b'pending')
    with pytest.raises((RuntimeError, ValueError), match='sidecar|journal'):
        manager(encrypted_database, tmp_path / 'backups').ensure()


def test_process_check_and_database_lock_block_access(encrypted_database, tmp_path, monkeypatch):
    import rekordbx_mcp.backup as backup
    a = manager(encrypted_database, tmp_path / 'backups')
    b = manager(encrypted_database, tmp_path / 'backups')
    with a.lock():
        with pytest.raises(RuntimeError, match='busy'):
            with b.lock():
                pytest.fail('must not acquire a second lock')
    monkeypatch.setattr(backup, 'require_rekordbox_closed', lambda: (_ for _ in ()).throw(RuntimeError('Close Rekordbox')))
    with pytest.raises(RuntimeError, match='Close Rekordbox'):
        a.ensure()


def test_restore_recovers_a_deleted_database(encrypted_database, tmp_path):
    m = manager(encrypted_database, tmp_path / 'backups')
    point = m.ensure()
    original = encrypted_database.read_bytes()
    encrypted_database.unlink()
    recovered = manager(encrypted_database, tmp_path / 'backups')
    recovered.restore(point.name)
    assert encrypted_database.read_bytes() == original
