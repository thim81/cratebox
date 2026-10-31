import subprocess

from rekordbx_mcp.launcher import serve


def test_invalid_snapshot_never_launches_worker(tmp_path, monkeypatch):
    def unexpected_launch(*args, **kwargs):
        raise AssertionError("Worker must not launch with an invalid snapshot")

    monkeypatch.setattr(subprocess, "run", unexpected_launch)
    try:
        serve(tmp_path)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("Missing snapshot database was accepted")
