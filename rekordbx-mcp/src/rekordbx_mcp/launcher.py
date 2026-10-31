"""Launch the MCP worker against a verified read-only snapshot."""

import os
import subprocess
import sys
from pathlib import Path

from .snapshot import verify_snapshot


def serve(snapshot: Path) -> int:
    snapshot = Path(snapshot).resolve(strict=True)
    verify_snapshot(snapshot)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONSTARTUP", None)
    env.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
    command = [
        sys.executable, "-m", "rekordbx_mcp.server", "--snapshot", str(snapshot),
    ]
    # Inherit only MCP stdio; no source database handles enter the worker.
    return subprocess.run(command, env=env, close_fds=True).returncode
