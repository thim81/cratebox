"""Paths and configuration shared by the CrateBox API modules."""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PLAYLIST_DIR = REPO_ROOT / "playlists"
STATE_DIRECTORY = REPO_ROOT / ".cratebox"
CRATE_DIRECTORY = STATE_DIRECTORY / "crates"
ARTWORK_FILE = STATE_DIRECTORY / "artwork.json"
OUTPUT_DIRECTORY = REPO_ROOT / "output"
PLAYLIST_DIR = Path(os.environ.get("PLAYLIST_DIR", str(DEFAULT_PLAYLIST_DIR))).expanduser().resolve()
