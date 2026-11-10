"""Launch the collection worker with an explicit original database path."""
import os
import subprocess
import sys
from pathlib import Path

from .backup import DEFAULT_BACKUP_DIRECTORY
from .snapshot import require_rekordbox_closed


def serve(source: Path, backup_directory: Path = DEFAULT_BACKUP_DIRECTORY) -> int:
    source = Path(source).absolute()
    require_rekordbox_closed()
    if source.is_symlink() or not source.is_file():
        raise ValueError('Select an existing database file, not a symlink.')
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONSTARTUP', None)
    env.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
    return subprocess.run([
        sys.executable, '-m', 'rekordbx_mcp.server', '--source', str(source),
        '--backup-directory', str(backup_directory),
    ], env=env, close_fds=True).returncode
