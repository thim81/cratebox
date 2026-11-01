import importlib.util
from pathlib import Path

import pytest
from fastapi import HTTPException


api_path = Path(__file__).resolve().parents[2] / "neon-crate" / "server.py"
api_spec = importlib.util.spec_from_file_location("cratedeck_local_api", api_path)
cratedeck_api = importlib.util.module_from_spec(api_spec)
sys.modules[api_spec.name] = cratedeck_api
api_spec.loader.exec_module(cratedeck_api)


def write_playlist_and_plan(tmp_path, playlist_audio: Path, plan_audio: Path):
    playlists = tmp_path / "playlists"
    output = tmp_path / "output"
    playlists.mkdir()
    output.mkdir()
    playlist = playlists / "Set.m3u8"
    playlist.write_text(f"#EXTM3U\n{playlist_audio}\n", encoding="utf-8")
    (output / "Set.json").write_text(
        f'{{"format":1,"name":"Set","tracks":[{{"track_id":"42","file_path":"{plan_audio}"}}]}}',
        encoding="utf-8",
    )
    return playlist, output


def test_playlist_api_keeps_audio_path_inside_server(tmp_path, monkeypatch):
    audio = tmp_path / "music" / "track.mp3"
    audio.parent.mkdir()
    audio.write_bytes(b"audio")
    playlist, output = write_playlist_and_plan(tmp_path, audio, audio)
    monkeypatch.setattr(cratedeck_api, "PLAN_DIRECTORY", output)
    monkeypatch.setattr(cratedeck_api.mutagen, "File", lambda *_args, **_kwargs: None)

    track = cratedeck_api.parse_playlist(playlist)[0]

    assert track["rekordbox_id"] == "42"
    assert "file_path" not in track


def test_playlist_api_rejects_a_plan_path_that_does_not_match_m3u(tmp_path, monkeypatch):
    playlist_audio = tmp_path / "music" / "playlist-track.mp3"
    plan_audio = tmp_path / "music" / "different-track.mp3"
    playlist_audio.parent.mkdir()
    playlist_audio.write_bytes(b"playlist audio")
    plan_audio.write_bytes(b"plan audio")
    playlist, output = write_playlist_and_plan(tmp_path, playlist_audio, plan_audio)
    monkeypatch.setattr(cratedeck_api, "PLAN_DIRECTORY", output)

    with pytest.raises(HTTPException) as error:
        cratedeck_api.parse_playlist(playlist)

    assert error.value.status_code == 409
