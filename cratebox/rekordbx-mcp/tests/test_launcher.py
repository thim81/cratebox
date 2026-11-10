import subprocess
import pytest

from rekordbx_mcp.launcher import serve


def test_missing_database_never_launches_worker(tmp_path, monkeypatch):
    monkeypatch.setattr('rekordbx_mcp.launcher.require_rekordbox_closed', lambda: None)
    monkeypatch.setattr(subprocess, 'run', lambda *_a, **_kw: pytest.fail('must not launch'))
    with pytest.raises(ValueError, match='existing database'):
        serve(tmp_path / 'missing.db')
