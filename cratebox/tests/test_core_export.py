import asyncio
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.export import export_playlist


def resolver_for(rows):
    async def resolve_tracks(**selector):
        if "track_ids" in selector:
            return [next(row for row in rows if row["id"] == item) for item in selector["track_ids"]]
        return [next(row for row in rows if row["file_path"] == path) for path in selector["file_paths"]]
    return resolve_tracks


def test_export_preserves_order_duplicates_and_keeps_audio_paths_out_of_result(tmp_path):
    first = tmp_path / "first.mp3"
    second = tmp_path / "second.mp3"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    by_id = {
        "1": {"id": "1", "file_path": str(first), "title": "First", "artist": "Artist", "duration": 10},
        "2": {"id": "2", "file_path": str(second), "title": "Second", "artist": "Guest", "duration": 20},
    }

    async def resolve_tracks(**selector):
        if "track_ids" in selector:
            return [by_id[track_id] for track_id in selector["track_ids"]]
        return [next(track for track in by_id.values() if track["file_path"] == path) for path in selector["file_paths"]]

    result = asyncio.run(export_playlist(
        "Warm up", track_ids=["2", "1", "2"], file_paths=None,
        resolve_tracks=resolve_tracks, crate_directory=tmp_path / "output",
        playlists_directory=tmp_path / "playlists",
    ))
    assert Path(result["playlist_path"]).read_text().splitlines() == [
        "#EXTM3U", str(second), str(first), str(second),
    ]
    plan = json.loads(Path(result["plan_path"]).read_text())
    assert [track["track_id"] for track in plan["tracks"]] == ["2", "1", "2"]
    assert plan["tracks"][1]["artist"] == "Artist"
    assert str(first) not in json.dumps(result)


def test_export_rejects_unknown_collection_tracks_without_writing(tmp_path):
    async def resolve_tracks(**_selector):
        return []

    with pytest.raises(ValueError, match="active collection"):
        asyncio.run(export_playlist(
            "Warm up", track_ids=["gone"], file_paths=None,
            resolve_tracks=resolve_tracks, crate_directory=tmp_path / "output",
            playlists_directory=tmp_path / "playlists",
        ))
    assert not (tmp_path / "output").exists()


def test_export_resolves_exact_file_locations_and_preserves_duplicates(tmp_path):
    rows = []
    for track_id, filename in [("1", "one.mp3"), ("2", "two.mp3")]:
        path = tmp_path / filename
        path.write_bytes(track_id.encode())
        rows.append({"id": track_id, "file_path": str(path), "title": track_id})
    locations = [rows[1]["file_path"], rows[0]["file_path"], rows[1]["file_path"]]
    result = asyncio.run(export_playlist(
        "From files", track_ids=None, file_paths=locations,
        resolve_tracks=resolver_for(rows), crate_directory=tmp_path / "output",
        playlists_directory=tmp_path / "playlists",
    ))
    plan = json.loads(Path(result["plan_path"]).read_text())
    assert [track["track_id"] for track in plan["tracks"]] == ["2", "1", "2"]
    assert Path(result["playlist_path"]).read_text().splitlines()[1:] == locations
    assert all(path not in json.dumps(result) for path in locations)


def test_export_requires_confirmation_and_updates_paired_files(tmp_path):
    audio = tmp_path / "one.mp3"
    audio.write_bytes(b"audio")
    rows = [{"id": "1", "file_path": str(audio), "title": "One"}]
    output, playlists = tmp_path / "output", tmp_path / "playlists"
    output.mkdir(); playlists.mkdir()
    playlist, plan = playlists / "Mix.m3u8", output / "Mix.json"
    playlist.write_text("old playlist")
    plan.write_text("old plan")
    with pytest.raises(FileExistsError):
        asyncio.run(export_playlist(
            "Mix", track_ids=["1"], file_paths=None, resolve_tracks=resolver_for(rows),
            crate_directory=output, playlists_directory=playlists,
        ))
    assert playlist.read_text() == "old playlist"
    assert plan.read_text() == "old plan"
    result = asyncio.run(export_playlist(
        "Mix", track_ids=["1"], file_paths=None, resolve_tracks=resolver_for(rows),
        crate_directory=output, playlists_directory=playlists, update_existing=True,
    ))
    assert result["updated_existing"] is True
    assert playlist.read_text().splitlines() == ["#EXTM3U", str(audio)]
    assert json.loads(plan.read_text())["tracks"][0]["track_id"] == "1"


def test_export_rolls_back_pair_write_without_leaving_backup_files(tmp_path, monkeypatch):
    import core.export as exporter

    audio = tmp_path / "one.mp3"
    audio.write_bytes(b"audio")
    rows = [{"id": "1", "file_path": str(audio), "title": "One"}]
    output, playlists = tmp_path / "output", tmp_path / "playlists"
    output.mkdir(); playlists.mkdir()
    playlist, plan = playlists / "Mix.m3u8", output / "Mix.json"
    playlist.write_text("old playlist")
    plan.write_text("old plan")
    real_replace = exporter.os.replace
    attempts = 0

    def fail_second_install(src, dst, **kwargs):
        nonlocal attempts
        if str(src).endswith(".tmp"):
            attempts += 1
            if attempts == 2:
                raise OSError("synthetic pair failure")
        return real_replace(src, dst, **kwargs)

    monkeypatch.setattr(exporter.os, "replace", fail_second_install)
    with pytest.raises(OSError, match="synthetic pair failure"):
        asyncio.run(export_playlist(
            "Mix", track_ids=["1"], file_paths=None, resolve_tracks=resolver_for(rows),
            crate_directory=output, playlists_directory=playlists, update_existing=True,
        ))
    assert playlist.read_text() == "old playlist"
    assert plan.read_text() == "old plan"
    assert {path.name for path in output.iterdir()} == {"Mix.json"}
    assert {path.name for path in playlists.iterdir()} == {"Mix.m3u8"}


def test_export_rejects_symlink_destination(tmp_path):
    audio = tmp_path / "one.mp3"
    audio.write_bytes(b"audio")
    rows = [{"id": "1", "file_path": str(audio)}]
    real_output = tmp_path / "real-output"
    real_output.mkdir()
    output_link = tmp_path / "output"
    output_link.symlink_to(real_output, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        asyncio.run(export_playlist(
            "Mix", track_ids=["1"], file_paths=None, resolve_tracks=resolver_for(rows),
            crate_directory=output_link, playlists_directory=tmp_path / "playlists",
        ))
    assert list(real_output.iterdir()) == []


def test_export_errors_do_not_echo_audio_paths(tmp_path):
    secret_path = "/private/audio/secret.mp3"

    async def resolve_tracks(**_selector):
        return [{"id": "gone", "file_path": secret_path}]

    with pytest.raises(ValueError) as error:
        asyncio.run(export_playlist(
            "Mix", track_ids=["gone"], file_paths=None, resolve_tracks=resolve_tracks,
            crate_directory=tmp_path / "output", playlists_directory=tmp_path / "playlists",
        ))
    assert secret_path not in str(error.value)
    assert not (tmp_path / "output").exists()


def test_export_resolves_only_configured_separator_files(tmp_path, monkeypatch):
    import core.export as exporter

    audio = tmp_path / "one.mp3"
    separator_directory = tmp_path / "separators"
    separator_directory.mkdir()
    separator_path = separator_directory / "Separator-90.wav"
    audio.write_bytes(b"audio")
    separator_path.write_bytes(b"separator")
    rows = [
        {"id": "1", "file_path": str(audio), "title": "One"},
        {"id": "sep", "file_path": str(separator_path), "title": "Separator"},
    ]
    monkeypatch.setattr(exporter, "SEPARATOR_DIRECTORY", separator_directory)
    result = asyncio.run(export_playlist(
        "With separator", track_ids=["1"], file_paths=None, resolve_tracks=resolver_for(rows),
        crate_directory=tmp_path / "output", playlists_directory=tmp_path / "playlists",
        separators=[{"type": "90s", "before_track": 1}],
    ))
    tracks = json.loads(Path(result["plan_path"]).read_text())["tracks"]
    assert [track["track_id"] for track in tracks] == ["sep", "1"]
    assert tracks[0]["separator_type"] == "90s"
    assert result["separator_count"] == 1
