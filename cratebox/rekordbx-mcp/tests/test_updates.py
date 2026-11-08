import subprocess
import pytest

from rekordbx_mcp.update import UPSTREAM_URL, update_upstream


OLD = "1" * 40
NEW = "2" * 40


@pytest.fixture
def project(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "fixture"\n'
        '[tool.uv.sources]\n'
        f'rekordbox-mcp = {{ git = "{UPSTREAM_URL}", rev = "{OLD}" }}\n'
    )
    (tmp_path / "uv.lock").write_bytes(b"original lockfile\n")
    return tmp_path


def fake_commands(monkeypatch, project, *, head=NEW, failure=None):
    # Substitute network and package installation only; exercise real metadata
    # edits and rollback. The MCP tests exercise the read-only connection.
    def run(command, **kwargs):
        if command[0] == "git":
            return subprocess.CompletedProcess(command, 0, stdout=f"{head}\tHEAD\n")
        if command[0] != "uv":
            pytest.fail(f"Unexpected update dependency: {command[0]}")
        if command[1] == "lock":
            (project / "uv.lock").write_bytes(b"candidate lockfile\n")
        if failure and failure in command:
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("rekordbx_mcp.update.subprocess.run", run)


def test_check_reports_new_revision_without_changing_files(project, monkeypatch):
    fake_commands(monkeypatch, project)
    before = (project / "pyproject.toml").read_bytes()
    result = update_upstream(project, check_only=True)
    assert "available" in result.lower()
    assert NEW in result
    assert (project / "pyproject.toml").read_bytes() == before
    assert (project / "uv.lock").read_bytes() == b"original lockfile\n"


def test_update_accepts_candidate_after_successful_checks(project, monkeypatch):
    fake_commands(monkeypatch, project)
    result = update_upstream(project)
    assert NEW in result
    assert f'rev = "{NEW}"' in (project / "pyproject.toml").read_text()
    assert (project / "uv.lock").read_bytes() == b"candidate lockfile\n"


@pytest.mark.parametrize("failure", ["lock", "sync", "pytest"])
def test_failed_update_restores_exact_existing_metadata(project, monkeypatch, failure):
    fake_commands(monkeypatch, project, failure=failure)
    before = (project / "pyproject.toml").read_bytes()
    with pytest.raises(RuntimeError, match="restored"):
        update_upstream(project)
    assert (project / "pyproject.toml").read_bytes() == before
    assert (project / "uv.lock").read_bytes() == b"original lockfile\n"


def test_already_latest_does_not_change_lockfile(project, monkeypatch):
    fake_commands(monkeypatch, project, head=OLD)
    assert "already" in update_upstream(project).lower()
    assert (project / "uv.lock").read_bytes() == b"original lockfile\n"


def test_bad_remote_response_leaves_files_untouched(project, monkeypatch):
    fake_commands(monkeypatch, project, head="not-a-commit")
    with pytest.raises(RuntimeError, match="commit"):
        update_upstream(project)
    assert OLD in (project / "pyproject.toml").read_text()
    assert (project / "uv.lock").read_bytes() == b"original lockfile\n"


def test_update_does_not_require_sandbox_executable(project, monkeypatch):
    fake_commands(monkeypatch, project)
    assert NEW in update_upstream(project)
