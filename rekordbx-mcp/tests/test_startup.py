import sys
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from rekordbx_mcp import cli
from rekordbx_mcp.snapshot import require_rekordbox_closed, verify_snapshot


def test_installed_command_runs_under_new_name():
    command = Path(sys.executable).parent / "rekordbx-mcp"
    result = subprocess.run([str(command), "--help"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "rekordbx-mcp" in result.stdout
    assert "update-upstream" in result.stdout


def startup_args(monkeypatch, source, destination):
    monkeypatch.setattr(sys, "argv", [
        "rekordbx-mcp", "start", "--source", str(source),
        "--destination", str(destination),
    ])


def test_start_copies_latest_source_before_serving(tmp_path, monkeypatch, capsys):
    source = tmp_path / "original" / "master.db"
    source.parent.mkdir()
    source.write_bytes(b"latest collection")
    destination = tmp_path / "snapshots"
    monkeypatch.setattr("rekordbx_mcp.snapshot.require_rekordbox_closed", lambda: None)
    startup_args(monkeypatch, source, destination)

    def serve(snapshot):
        database = verify_snapshot(snapshot)
        assert database.read_bytes() == b"latest collection"
        assert database.stat().st_mode & 0o222 == 0
        assert source.read_bytes() == b"latest collection"
        return 37

    monkeypatch.setattr("rekordbx_mcp.launcher.serve", serve)
    with pytest.raises(SystemExit) as stopped:
        cli.main()
    assert stopped.value.code == 37
    assert capsys.readouterr().out == ""  # stdout belongs exclusively to MCP.


def test_each_start_uses_a_new_copy_of_current_data(tmp_path, monkeypatch):
    source = tmp_path / "original" / "master.db"
    source.parent.mkdir()
    destination = tmp_path / "snapshots"
    monkeypatch.setattr("rekordbx_mcp.snapshot.require_rekordbox_closed", lambda: None)
    startup_args(monkeypatch, source, destination)
    copies = []

    def serve(snapshot):
        copies.append(verify_snapshot(snapshot))
        return 0

    monkeypatch.setattr("rekordbx_mcp.launcher.serve", serve)
    for content in (b"first collection", b"updated collection"):
        source.write_bytes(content)
        with pytest.raises(SystemExit) as stopped:
            cli.main()
        assert stopped.value.code == 0
    assert copies[0] != copies[1]
    assert copies[0].read_bytes() == b"first collection"
    assert copies[1].read_bytes() == b"updated collection"


@pytest.mark.parametrize("name", ["rekordbox", "rekordboxAgent", "Rekordbox 7"])
def test_start_refuses_running_rekordbox_without_reusing_old_copy(
    tmp_path, monkeypatch, name, capsys,
):
    source = tmp_path / "original" / "master.db"
    source.parent.mkdir()
    source.write_bytes(b"latest collection")
    destination = tmp_path / "snapshots"
    destination.mkdir()
    old_copy = destination / "old-copy"
    old_copy.mkdir()
    (old_copy / "master.db").write_bytes(b"stale collection")
    monkeypatch.setattr("rekordbx_mcp.snapshot.psutil.process_iter", lambda *_: [
        SimpleNamespace(info={"name": name}),
    ])
    startup_args(monkeypatch, source, destination)

    def forbidden_serve(_snapshot):
        pytest.fail("MCP must not start when Rekordbox is running")

    monkeypatch.setattr("rekordbx_mcp.launcher.serve", forbidden_serve)
    with pytest.raises(SystemExit) as stopped:
        cli.main()
    assert stopped.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "Close Rekordbox" in output.err
    assert list(destination.iterdir()) == [old_copy]


def test_unreadable_process_name_refuses_startup(monkeypatch):
    monkeypatch.setattr("rekordbx_mcp.snapshot.psutil.process_iter", lambda *_: [
        SimpleNamespace(info={"name": None}),
    ])
    with pytest.raises(RuntimeError, match="verify"):
        require_rekordbox_closed()


def test_rekordbox_reopening_during_copy_prevents_mcp_start(tmp_path, monkeypatch):
    source = tmp_path / "original" / "master.db"
    source.parent.mkdir()
    source.write_bytes(b"collection")
    destination = tmp_path / "snapshots"
    checks = iter([None, RuntimeError("Rekordbox reopened")])

    def check():
        result = next(checks)
        if result:
            raise result

    monkeypatch.setattr("rekordbx_mcp.snapshot.require_rekordbox_closed", check)
    startup_args(monkeypatch, source, destination)
    monkeypatch.setattr(
        "rekordbx_mcp.launcher.serve",
        lambda _: pytest.fail("An incomplete copy must not be served"),
    )
    with pytest.raises(SystemExit) as stopped:
        cli.main()
    assert stopped.value.code == 1
    assert not list(destination.glob("*/manifest.json"))
