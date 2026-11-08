import json
from pathlib import Path
import sys

import pytest
from fastapi import HTTPException


CRATEBOX_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = CRATEBOX_ROOT.parent
sys.path.insert(0, str(CRATEBOX_ROOT))
from api import config, playlists
from api import artwork_data
from core import export as core_export


def test_cratebox_owned_json_defaults_to_hidden_state_directory():
    assert config.STATE_DIRECTORY == REPOSITORY_ROOT / ".cratebox"
    assert config.CRATE_DIRECTORY == config.STATE_DIRECTORY / "crates"
    assert config.ARTWORK_FILE == config.STATE_DIRECTORY / "artwork.json"
    assert config.OUTPUT_DIRECTORY == REPOSITORY_ROOT / "output"
    assert core_export.CRATE_DIRECTORY == config.CRATE_DIRECTORY


def test_existing_output_playlist_plan_is_ignored_and_left_untouched(tmp_path, monkeypatch):
    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"audio")
    playlist = tmp_path / "Set.m3u8"
    playlist.write_text(f"#EXTM3U\n{audio}\n", encoding="utf-8")
    output_directory = tmp_path / "output"
    output_directory.mkdir()
    existing_plan = output_directory / "Set.json"
    existing_plan.write_text(json.dumps({
        "format": 1,
        "name": "Set",
        "tracks": [{"track_id": "42", "file_path": str(audio)}],
    }), encoding="utf-8")
    current_directory = tmp_path / ".cratebox" / "crates"
    monkeypatch.setattr(playlists, "CRATE_DIRECTORY", current_directory)
    monkeypatch.setattr(playlists.mutagen, "File", lambda *_args, **_kwargs: None)

    records = playlists.parse_playlist(playlist)

    assert records[0]["rekordbox_id"] is None
    assert existing_plan.exists()
    assert not (current_directory / "Set.json").exists()


def test_hidden_state_symlink_is_rejected(tmp_path, monkeypatch):
    playlist = tmp_path / "Set.m3u8"
    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"audio")
    playlist.write_text(f"#EXTM3U\n{audio}\n", encoding="utf-8")
    real_state = tmp_path / "real-state"
    real_state.mkdir()
    (tmp_path / ".cratebox").symlink_to(real_state, target_is_directory=True)
    monkeypatch.setattr(playlists, "CRATE_DIRECTORY", tmp_path / ".cratebox" / "crates")
    monkeypatch.setattr(playlists.mutagen, "File", lambda *_args, **_kwargs: None)

    with pytest.raises(HTTPException) as error:
        playlists.parse_playlist(playlist)

    assert error.value.status_code == 409


def test_existing_output_artwork_overrides_are_ignored(tmp_path, monkeypatch):
    existing_file = tmp_path / "output" / "cratebox-artwork.json"
    existing_file.parent.mkdir()
    previous_data = {"playlists": {"Set": "https://images.example/cover.png"}, "tracks": {}}
    existing_file.write_text(json.dumps(previous_data), encoding="utf-8")
    current_directory = tmp_path / ".cratebox"
    current_file = current_directory / "artwork.json"
    monkeypatch.setattr(artwork_data, "ARTWORK_FILE", current_file)
    assert artwork_data.read_artwork_overrides() == {"playlists": {}, "tracks": {}}
    assert not current_file.exists()
    assert existing_file.exists()
