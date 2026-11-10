import json
from pathlib import Path
import sys

import pytest
from fastapi import HTTPException


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "cratebox"))
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
    monkeypatch.setattr(playlists, "CRATE_DIRECTORY", output)
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
        "cue_count": 2, "playlist_count": 1, "play_count": 17,
        "playlists": [{"id": "rb-1", "name": "Favorites"}],
    })
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    monkeypatch.setattr(playlists, "CRATE_DIRECTORY", output)
    monkeypatch.setattr(playlists.mutagen, "File", lambda *_args, **_kwargs: None)

    track = playlists.parse_playlist(playlist)[0]

    assert (track["title"], track["artist"], track["album"]) == (
        "Plan title", "Plan artist", "Plan album",
    )
    assert (track["genre"], track["bpm"], track["key"], track["rating"], track["duration"]) == (
        "House", 123.45, "8A", 4, 321,
    )
    assert (track["cue_count"], track["playlist_count"], track["play_count"]) == (2, 1, 17)
    assert track["playlists"] == [{"id": "rb-1", "name": "Favorites"}]
    assert "file_path" not in track


def test_playlist_api_rejects_a_plan_path_that_does_not_match_m3u(tmp_path, monkeypatch):
    playlist_audio = tmp_path / "music" / "playlist-track.mp3"
    plan_audio = tmp_path / "music" / "different-track.mp3"
    playlist_audio.parent.mkdir()
    playlist_audio.write_bytes(b"playlist audio")
    plan_audio.write_bytes(b"plan audio")
    playlist, output = write_playlist_and_plan(tmp_path, playlist_audio, plan_audio)
    monkeypatch.setattr(playlists, "CRATE_DIRECTORY", output)

    with pytest.raises(HTTPException) as error:
        playlists.parse_playlist(playlist)

    assert error.value.status_code == 409


def test_playlist_list_ignores_export_m3u_without_crate_record(tmp_path, monkeypatch):
    playlists_dir = tmp_path / "playlists"
    crate_dir = tmp_path / ".cratebox" / "crates"
    playlists_dir.mkdir()
    crate_dir.mkdir(parents=True)
    (playlists_dir / "Existing export.m3u8").write_text("#EXTM3U\n", encoding="utf-8")
    (playlists_dir / "Local crate.m3u8").write_text("#EXTM3U\n", encoding="utf-8")
    (crate_dir / "Local crate.json").write_text(json.dumps({
        "format": 1, "name": "Local crate", "tracks": [],
    }), encoding="utf-8")
    monkeypatch.setattr(playlists, "PLAYLIST_DIR", playlists_dir)
    monkeypatch.setattr(playlists, "CRATE_DIRECTORY", crate_dir)

    listed = playlists.list_playlists()

    assert [playlist["id"] for playlist in listed] == ["Local crate"]


def test_rename_playlist_endpoint_keeps_plan_and_artwork_overrides_attached(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from api import artwork_data
    from api.app import app as api_app

    playlist_audio = tmp_path / "music" / "track.mp3"
    playlist_audio.parent.mkdir()
    playlist_audio.write_bytes(b"audio")
    playlist_dir = tmp_path / "playlists"
    crate_dir = tmp_path / ".cratebox" / "crates"
    playlist_dir.mkdir()
    crate_dir.mkdir(parents=True)
    playlist_path = playlist_dir / "Set.m3u8"
    playlist_path.write_text(f"#EXTM3U\n{playlist_audio}\n", encoding="utf-8")
    art_file = tmp_path / ".cratebox" / "artwork.json"
    art_file.write_text(json.dumps({
        "playlists": {"Set": "https://example.test/cover.jpg"},
        "tracks": {"Set": {"42-1": "https://example.test/track.jpg"}},
    }), encoding="utf-8")
    (crate_dir / "Set.json").write_text(json.dumps({
        "format": 1,
        "name": "Set",
        "tracks": [{"track_id": "42", "file_path": str(playlist_audio)}],
    }), encoding="utf-8")
    monkeypatch.setattr(playlists, "PLAYLIST_DIR", playlist_dir)
    monkeypatch.setattr(playlists, "DEFAULT_PLAYLIST_DIR", playlist_dir)
    monkeypatch.setattr(playlists, "CRATE_DIRECTORY", crate_dir)
    monkeypatch.setattr(artwork_data, "ARTWORK_FILE", art_file)

    with TestClient(api_app) as client:
        response = client.patch("/api/playlists/Set", json={"name": "Warm Up"})

    assert response.status_code == 200, response.text
    assert response.json() == {"id": "Warm Up", "name": "Warm Up"}
    assert not (playlist_dir / "Set.m3u8").exists()
    assert (playlist_dir / "Warm Up.m3u8").read_text(encoding="utf-8").splitlines() == [
        "#EXTM3U", str(playlist_audio),
    ]
    plan = json.loads((crate_dir / "Warm Up.json").read_text(encoding="utf-8"))
    assert (plan["name"], plan["tracks"][0]["track_id"]) == ("Warm Up", "42")
    assert json.loads(art_file.read_text(encoding="utf-8")) == {
        "playlists": {"Warm Up": "https://example.test/cover.jpg"},
        "tracks": {"Warm Up": {"42-1": "https://example.test/track.jpg"}},
    }


def test_download_playlist_endpoint_returns_only_m3u8(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from api.app import app as api_app

    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"audio")
    playlist_dir = tmp_path / "playlists"
    crate_dir = tmp_path / ".cratebox" / "crates"
    playlist_dir.mkdir()
    crate_dir.mkdir(parents=True)
    playlist = playlist_dir / "Set.m3u8"
    playlist.write_text(f"#EXTM3U\n{audio}\n", encoding="utf-8")
    (crate_dir / "Set.json").write_text(json.dumps({
        "format": 1,
        "name": "Set",
        "tracks": [{"track_id": "42", "file_path": str(audio)}],
    }), encoding="utf-8")
    monkeypatch.setattr(playlists, "PLAYLIST_DIR", playlist_dir)
    monkeypatch.setattr(playlists, "DEFAULT_PLAYLIST_DIR", playlist_dir)
    monkeypatch.setattr(playlists, "CRATE_DIRECTORY", crate_dir)

    with TestClient(api_app) as client:
        response = client.get("/api/playlists/Set/download")

    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="Set.m3u8"'
    assert response.content == playlist.read_bytes()
    assert b'"tracks"' not in response.content


def test_delete_playlist_endpoint_removes_playlist_and_plan_but_keeps_audio(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from api.app import app as api_app

    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"audio")
    playlist_dir = tmp_path / "playlists"
    crate_dir = tmp_path / ".cratebox" / "crates"
    playlist_dir.mkdir()
    crate_dir.mkdir(parents=True)
    (playlist_dir / "Set.m3u8").write_text(f"#EXTM3U\n{audio}\n", encoding="utf-8")
    (crate_dir / "Set.json").write_text(json.dumps({
        "format": 1,
        "name": "Set",
        "tracks": [{"track_id": "42", "file_path": str(audio)}],
    }), encoding="utf-8")
    monkeypatch.setattr(playlists, "PLAYLIST_DIR", playlist_dir)
    monkeypatch.setattr(playlists, "DEFAULT_PLAYLIST_DIR", playlist_dir)
    monkeypatch.setattr(playlists, "CRATE_DIRECTORY", crate_dir)

    with TestClient(api_app) as client:
        response = client.delete("/api/playlists/Set")

    assert response.status_code == 200, response.text
    assert response.json() == {"deleted": "Set"}
    assert not (playlist_dir / "Set.m3u8").exists()
    assert not (crate_dir / "Set.json").exists()
    assert audio.read_bytes() == b"audio"
