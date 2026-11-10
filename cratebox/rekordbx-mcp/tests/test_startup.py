"""Direct startup never copies a collection or falls back to a snapshot."""
import sys
from types import SimpleNamespace

import pytest

from rekordbx_mcp import cli
from rekordbx_mcp.snapshot import require_rekordbox_closed


def test_start_serves_explicit_original_database(tmp_path, monkeypatch, capsys):
    source = tmp_path / 'master.db'
    source.write_bytes(b'fixture')
    monkeypatch.setattr('rekordbx_mcp.snapshot.psutil.process_iter', lambda *_: [])
    monkeypatch.setattr(sys, 'argv', ['rekordbx-mcp', 'start', '--source', str(source)])
    calls = []
    monkeypatch.setattr('rekordbx_mcp.launcher.serve', lambda source, backups: calls.append(source) or 37)
    with pytest.raises(SystemExit) as stopped:
        cli.main()
    assert stopped.value.code == 37
    assert calls == [source]
    assert capsys.readouterr().out == ''


@pytest.mark.parametrize('name', ['rekordbox', 'rekordboxAgent', 'Rekordbox 7', None])
def test_start_refuses_running_or_unreadable_processes(tmp_path, monkeypatch, capsys, name):
    monkeypatch.setattr('rekordbx_mcp.snapshot.psutil.process_iter', lambda *_: [SimpleNamespace(info={'name':name})])
    monkeypatch.setattr(sys, 'argv', ['rekordbx-mcp', 'start'])
    monkeypatch.setattr('rekordbx_mcp.launcher.serve', lambda *_: pytest.fail('must not start'))
    with pytest.raises(SystemExit) as stopped:
        cli.main()
    assert stopped.value.code == 1
    assert 'Rekordbox' in capsys.readouterr().err


def test_process_inventory_permission_failure_is_clear(monkeypatch):
    def denied(*_):
        raise PermissionError('denied')
    monkeypatch.setattr('rekordbx_mcp.snapshot.psutil.process_iter', denied)
    with pytest.raises(RuntimeError, match='process inspection failed'):
        require_rekordbox_closed()
