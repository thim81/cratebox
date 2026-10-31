"""Explicit upstream updates with compatibility checks and metadata rollback."""

import re
import subprocess
import sys
import tomllib
from pathlib import Path


UPSTREAM_URL = "https://github.com/davehenke/rekordbox-mcp"


def update_upstream(project: Path, *, check_only: bool = False) -> str:
    project = Path(project).resolve(strict=True)
    manifest = project / "pyproject.toml"
    lock = project / "uv.lock"
    if manifest.is_symlink() or lock.is_symlink():
        raise RuntimeError("Dependency metadata must not be symlinks.")
    original_manifest = manifest.read_bytes()
    original_lock = lock.read_bytes()
    source = tomllib.loads(original_manifest.decode())["tool"]["uv"]["sources"]["rekordbox-mcp"]
    current = source.get("rev", "")
    if source.get("git") != UPSTREAM_URL or not re.fullmatch(r"[0-9a-f]{40}", current):
        raise RuntimeError("Expected a pinned upstream Git source in pyproject.toml.")
    try:
        remote = subprocess.run(
            ["git", "ls-remote", UPSTREAM_URL + ".git", "HEAD"],
            check=True, capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("Could not query the upstream repository; no files changed.") from error
    match = re.fullmatch(r"([0-9a-f]{40})\s+HEAD\s*", remote.stdout)
    if not match:
        raise RuntimeError("Upstream returned an invalid commit; no files changed.")
    latest = match[1]
    if latest == current:
        return f"Already using latest upstream commit {current}."
    if check_only:
        return f"Update available: {current} -> {latest}."

    pin = f'rev = "{current}"'.encode()
    if original_manifest.count(pin) != 1:
        raise RuntimeError("Expected one inline revision pin; no files changed.")
    print(f"Updating upstream {current} -> {latest}; running compatibility tests.", file=sys.stderr)
    try:
        manifest.write_bytes(original_manifest.replace(pin, f'rev = "{latest}"'.encode(), 1))
        subprocess.run(
            ["uv", "lock", "--upgrade-package", "rekordbox-mcp"],
            cwd=project, check=True,
        )
        subprocess.run(["uv", "sync", "--locked"], cwd=project, check=True)
        subprocess.run(
            ["uv", "run", "--locked", "--no-sync", "pytest", "-q"],
            cwd=project, check=True,
        )
    except BaseException as error:
        # Preserve existing user edits exactly, including lockfile formatting.
        manifest.write_bytes(original_manifest)
        lock.write_bytes(original_lock)
        try:
            subprocess.run(["uv", "sync", "--locked"], cwd=project, check=True)
        except (OSError, subprocess.SubprocessError) as recovery_error:
            raise RuntimeError(
                "Update failed; previous dependency files restored. Environment recovery "
                "also failed; run 'uv sync --locked' before starting MCP."
            ) from recovery_error
        if isinstance(error, KeyboardInterrupt):
            raise
        raise RuntimeError(
            "Update failed; previous dependency files and environment restored."
        ) from error
    return f"Updated to upstream commit {latest}; compatibility tests passed."
