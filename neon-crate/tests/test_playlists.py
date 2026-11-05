import json
from pathlib import Path
import sys

import pytest
from fastapi import HTTPException


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "neon-crate"))
from api import playlists


def write_playlist_and_plan(tmp_path, playlist_audio: Path, plan_audio: Path):
    output = tmp_path / "output"
    output.mkdir()
    playlist = tmp_path / "Set.m3u8"
    playlist.write_text(f"#EXTM3U\n{playlist_audio}\n", encoding="utf-8")
    (output / "Set.json").write_text(
        json.dumps({
            "format": 1,
            "name": "Set",
            "tracks": [{"track_id": "42", "file_path": str(plan_audio)}],
        }),
        encoding="utf-8",
    )
    return playlist, output


def test_playlist_api_keeps_audio_path_inside_server(tmp_path, monkeypatch):
    audio = tmp_path / "music" / "track.mp3"
    audio.parent.mkdir()
    audio.write_bytes(b"audio")
    playlist, output = write_playlist_and_plan(tmp_path, audio, audio)
    monkeypatch.setattr(playlists, "PLAN_DIRECTORY", output)
    monkeypatch.setattr(playlists.mutagen, "File", lambda *_args, **_kwargs: None)

    track = playlists.parse_playlist(playlist)[0]

    assert track["rekordbox_id"] == "42"
    assert "file_path" not in track


def test_playlist_api_uses_rekordbox_metadata_from_json_plan(tmp_path, monkeypatch):
    audio = tmp_path / "music" / "track.mp3"
    audio.parent.mkdir()
    audio.write_bytes(b"audio")
    playlist, output = write_playlist_and_plan(tmp_path, audio, audio)
    plan_path = output / "Set.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["tracks"][0].update({
        "title": "Plan title", "artist": "Plan artist", "album": "Plan album",
        "genre": "House", "bpm": 123.45, "key": "8A", "rating": 4,
        "duration": 321,
    })
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    monkeypatch.setattr(playlists, "PLAN_DIRECTORY", output)
    monkeypatch.setattr(playlists.mutagen, "File", lambda *_args, **_kwargs: None)

    track = playlists.parse_playlist(playlist)[0]

    assert (track["title"], track["artist"], track["album"]) == (
        "Plan title", "Plan artist", "Plan album",
    )
    assert (track["genre"], track["bpm"], track["key"], track["rating"], track["duration"]) == (
        "House", 123.45, "8A", 4, 321,
    )


def test_playlist_api_rejects_a_plan_path_that_does_not_match_m3u(tmp_path, monkeypatch):
    playlist_audio = tmp_path / "music" / "playlist-track.mp3"
    plan_audio = tmp_path / "music" / "different-track.mp3"
    playlist_audio.parent.mkdir()
    playlist_audio.write_bytes(b"playlist audio")
    plan_audio.write_bytes(b"plan audio")
    playlist, output = write_playlist_and_plan(tmp_path, playlist_audio, plan_audio)
    monkeypatch.setattr(playlists, "PLAN_DIRECTORY", output)

    with pytest.raises(HTTPException) as error:
        playlists.parse_playlist(playlist)

    assert error.value.status_code == 409
