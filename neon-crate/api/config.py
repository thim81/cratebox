"""Paths and configuration shared by the CrateDeck API modules."""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PLAYLIST_DIR = REPO_ROOT / "playlists"
PLAN_DIRECTORY = REPO_ROOT / "output"
ARTWORK_FILE = PLAN_DIRECTORY / "cratedeck-artwork.json"
PLAYLIST_DIR = Path(os.environ.get("PLAYLIST_DIR", str(DEFAULT_PLAYLIST_DIR))).expanduser().resolve()
