import json
from pathlib import Path
import sys
import asyncio

import pytest

CRATEBOX_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CRATEBOX_ROOT))
from core.crates import (
    ApplicationConflict,
    ApplicationError,
    ApplicationNotFound,
    append_crate_tracks,
    create_crate,
    parse_crate_tracks,
    insert_crate_separator,
    insert_crate_track,
    playlist_entries,
    read_plan_ids,
    remove_crate_tracks,
    replace_crate_separator,
    reorder_crate_tracks,
    replace_crate_track,
)
from core import crates as crate_core


def test_crate_parser_preserves_duplicate_track_order_and_identity(tmp_path):
    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"audio")
    playlist = tmp_path / "Set.m3u8"
    lines = ["#EXTM3U\n", f"{audio}\n", f"{audio}\n"]
    crate_directory = tmp_path / ".cratebox" / "crates"
    crate_directory.mkdir(parents=True)
    (crate_directory / "Set.json").write_text(json.dumps({"tracks": [
        {"track_id": "42", "file_path": str(audio)},
        {"track_id": "42", "file_path": str(audio)},
    ]}))

    path, plan = read_plan_ids(playlist, lines, crate_directory)
    entries = list(playlist_entries(playlist, lines, plan))

    assert path == crate_directory / "Set.json"
    assert [(entry[1], entry[3], entry[4]) for entry in entries] == [
        (0, "42-1", "42"), (1, "42-2", "42"),
    ]


def test_crate_parser_rejects_plan_audio_path_mismatch(tmp_path):
    playlist_audio = tmp_path / "playlist.mp3"
    plan_audio = tmp_path / "other.mp3"
    playlist_audio.write_bytes(b"audio")
    plan_audio.write_bytes(b"audio")
    playlist = tmp_path / "Set.m3u8"
    playlist.write_text(f"#EXTM3U\n{playlist_audio}\n", encoding="utf-8")
    crate_directory = tmp_path / ".cratebox" / "crates"
    crate_directory.mkdir(parents=True)
    (crate_directory / "Set.json").write_text(json.dumps({"tracks": [
        {"track_id": "42", "file_path": str(plan_audio)},
    ]}))

    with pytest.raises(ApplicationConflict, match="out of sync"):
        read_plan_ids(playlist, playlist.read_text().splitlines(True), crate_directory)


def test_crate_track_parser_prefers_saved_metadata_and_keeps_file_location_internal(tmp_path):
    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"audio")
    playlist = tmp_path / "Set.m3u8"
    playlist.write_text(f"#EXTM3U\n{audio}\n", encoding="utf-8")
    crate_directory = tmp_path / ".cratebox" / "crates"
    crate_directory.mkdir(parents=True)
    (crate_directory / "Set.json").write_text(json.dumps({"tracks": [{
        "track_id": "42", "file_path": str(audio), "title": "Saved title",
        "artist": "Saved artist", "duration": 123, "rating": 4,
    }]}))

    records = parse_crate_tracks(
        playlist, crate_directory, media_reader=lambda _path, **_options: None,
    )

    assert records == [{
        "id": "42-1", "playlist_id": "Set", "rekordbox_id": "42",
        "title": "Saved title", "artist": "Saved artist", "album": "",
        "genre": "", "duration": 123, "rating": 4, "play_count": 0,
        "cue_count": 0, "playlist_count": 0, "playlists": [], "bpm": 0.0,
        "key": "", "quality": "MP3 0kbps", "_audio_path": audio,
    }]


def test_crate_track_parser_prefers_embedded_rating_over_saved_plan_rating(tmp_path):
    from mutagen.id3 import POPM
    from mutagen.mp3 import MP3
    import mutagen

    audio = tmp_path / "track.mp3"
    audio.write_bytes((bytes.fromhex("fffb9064") + bytes(413)) * 20)
    media = MP3(audio)
    media.add_tags()
    media.tags.add(POPM(email="cratebox", rating=204, count=0))
    media.save(v2_version=3)
    playlist = tmp_path / "Set.m3u8"
    playlist.write_text(f"#EXTM3U\n{audio}\n", encoding="utf-8")
    crate_directory = tmp_path / ".cratebox" / "crates"
    crate_directory.mkdir(parents=True)
    (crate_directory / "Set.json").write_text(json.dumps({"tracks": [{
        "track_id": "42", "file_path": str(audio), "rating": 2,
    }]}))

    records = parse_crate_tracks(playlist, crate_directory, media_reader=mutagen.File)

    assert records[0]["rating"] == 4


def test_create_crate_writes_empty_m3u_and_json_pair(tmp_path):
    playlists = tmp_path / "playlists"
    crates = tmp_path / ".cratebox" / "crates"
    playlists.mkdir()

    result = create_crate(" Warm Up ", playlists, crates, playlists)

    assert result == playlists / "Warm Up.m3u8"
    assert (playlists / "Warm Up.m3u8").read_text() == "#EXTM3U\n"
    assert json.loads((crates / "Warm Up.json").read_text()) == {
        "format": 1, "name": "Warm Up", "tracks": [],
    }


def test_remove_tracks_keeps_m3u_and_crate_records_in_sync(tmp_path):
    playlists, crates, audio_paths = _write_crate(tmp_path, ["42", "43", "42"])

    result = remove_crate_tracks(
        "Set", ["42-2"], playlists, crates, playlists,
    )

    assert result == {"removed": 1}
    assert (playlists / "Set.m3u8").read_text().splitlines() == [
        "#EXTM3U", str(audio_paths[0]), str(audio_paths[1]),
    ]
    assert [item["track_id"] for item in json.loads((crates / "Set.json").read_text())["tracks"]] == ["42", "43"]


def test_remove_tracks_rejects_stale_row_without_changing_either_file(tmp_path):
    playlists, crates, _ = _write_crate(tmp_path, ["42"])
    before_playlist = (playlists / "Set.m3u8").read_bytes()
    before_crate = (crates / "Set.json").read_bytes()

    with pytest.raises(ApplicationNotFound, match="Track not found"):
        remove_crate_tracks("Set", ["stale-row"], playlists, crates, playlists)

    assert (playlists / "Set.m3u8").read_bytes() == before_playlist
    assert (crates / "Set.json").read_bytes() == before_crate


def test_failed_second_write_restores_original_playlist_and_crate(tmp_path, monkeypatch):
    playlists, crates, _ = _write_crate(tmp_path, ["42", "43"])
    playlist, crate = playlists / "Set.m3u8", crates / "Set.json"
    before_playlist, before_crate = playlist.read_bytes(), crate.read_bytes()
    write = crate_core.atomic_write

    def fail_crate_write(path, content):
        if Path(path) == crate and content != before_crate.decode():
            raise OSError("simulated paired-write failure")
        return write(path, content)

    monkeypatch.setattr(crate_core, "atomic_write", fail_crate_write)
    with pytest.raises(ApplicationError, match="Could not update playlist"):
        remove_crate_tracks("Set", ["42-1"], playlists, crates, playlists)

    assert playlist.read_bytes() == before_playlist
    assert crate.read_bytes() == before_crate


def test_reorder_tracks_preserves_extinf_blocks_and_crate_metadata_order(tmp_path):
    playlists, crates, audio_paths = _write_crate(tmp_path, ["1", "2", "3"], extinf=True)

    result = reorder_crate_tracks(
        "Set", ["3-1"], "1-1", True, playlists, crates, playlists,
    )

    lines = (playlists / "Set.m3u8").read_text().splitlines()
    assert [line for line in lines if line.startswith("#EXTINF:")] == [
        "#EXTINF:3,Track 3", "#EXTINF:1,Track 1", "#EXTINF:2,Track 2",
    ]
    assert [line for line in lines if not line.startswith("#")] == [
        str(audio_paths[2]), str(audio_paths[0]), str(audio_paths[1]),
    ]
    assert [item["track_id"] for item in json.loads((crates / "Set.json").read_text())["tracks"]] == ["3", "1", "2"]
    assert result == {"moved": True}


def test_replace_track_updates_file_and_drops_stale_metadata(tmp_path):
    playlists, crates, audio_paths = _write_crate(tmp_path, ["42"])
    replacement = tmp_path / "replacement.mp3"
    replacement.write_bytes(b"replacement")

    result = replace_crate_track(
        "Set", "42-1", "99", replacement, playlists, crates, playlists,
    )

    assert result == {"track_id": "99-1"}
    assert (playlists / "Set.m3u8").read_text().splitlines() == ["#EXTM3U", str(replacement)]
    track = json.loads((crates / "Set.json").read_text())["tracks"][0]
    assert (track["track_id"], track["file_path"]) == ("99", str(replacement))
    assert "title" not in track and "rating" not in track


def test_append_crate_tracks_validates_existing_snapshot_then_appends_in_order(tmp_path):
    playlists, crates, audio_paths = _write_crate(tmp_path, ["42", "43"])
    extra = tmp_path / "extra.mp3"
    extra.write_bytes(b"extra")
    tracks = {
        "42": {"id": "42", "file_path": str(audio_paths[0]), "title": "One"},
        "43": {"id": "43", "file_path": str(audio_paths[1]), "title": "Two"},
        "99": {"id": "99", "file_path": str(extra), "title": "Three"},
    }

    async def resolve_tracks(**selector):
        return [tracks[track_id] for track_id in selector["track_ids"]]

    result = asyncio.run(append_crate_tracks(
        "Set", ["99"], resolve_tracks, playlists, crates, playlists,
    ))

    assert result["track_count"] == 3
    assert [item["track_id"] for item in json.loads((crates / "Set.json").read_text())["tracks"]] == [
        "42", "43", "99",
    ]
    assert (playlists / "Set.m3u8").read_text().splitlines() == [
        "#EXTM3U", *(tracks[track_id]["file_path"] for track_id in ("42", "43", "99")),
    ]


def test_insert_crate_track_after_duplicate_row_uses_row_occurrence(tmp_path):
    playlists, crates, audio_paths = _write_crate(tmp_path, ["42", "42"])
    extra = tmp_path / "extra.mp3"
    extra.write_bytes(b"extra")
    tracks = {
        "42": {"id": "42", "file_path": str(audio_paths[0]), "title": "Existing"},
        "99": {"id": "99", "file_path": str(extra), "title": "Inserted"},
    }

    async def resolve_tracks(**selector):
        return [tracks[track_id] for track_id in selector["track_ids"]]

    result = asyncio.run(insert_crate_track(
        "Set", "99", "42-2", resolve_tracks, playlists, crates, playlists,
    ))

    assert result["track_id"] == "99-1"
    assert [item["track_id"] for item in json.loads((crates / "Set.json").read_text())["tracks"]] == [
        "42", "42", "99",
    ]


def test_insert_crate_separator_resolves_fixed_file_and_updates_both_artifacts(tmp_path, monkeypatch):
    from core import export as crate_export

    playlists, crates, audio_paths = _write_crate(tmp_path, ["42"])
    separator_directory = tmp_path / "separators"
    separator_directory.mkdir()
    separator = separator_directory / "Separator.wav"
    separator.write_bytes(b"separator")
    monkeypatch.setattr(crate_export, "SEPARATOR_DIRECTORY", separator_directory)
    by_id = {
        "42": {"id": "42", "file_path": str(audio_paths[0]), "title": "Track"},
        "228753448": {"id": "228753448", "file_path": str(separator), "title": "Separator"},
    }

    async def resolve_tracks(**selector):
        if "track_ids" in selector:
            return [by_id[track_id] for track_id in selector["track_ids"]]
        return [by_id["228753448"]]

    result = asyncio.run(insert_crate_separator(
        "Set", "generic", "42-1", resolve_tracks, playlists, crates, playlists,
    ))

    records = json.loads((crates / "Set.json").read_text())["tracks"]
    assert [item["track_id"] for item in records] == ["42", "228753448"]
    assert records[1]["separator_type"] == "generic"
    assert result["track_count"] == 1 and result["separator_count"] == 1


def test_replace_crate_separator_uses_registered_fixed_track_and_updates_pair(tmp_path, monkeypatch):
    from core import export as crate_export

    playlists = tmp_path / "playlists"
    crates = tmp_path / ".cratebox" / "crates"
    separators = tmp_path / "separators"
    playlists.mkdir()
    crates.mkdir(parents=True)
    separators.mkdir()
    current = separators / "Separator.wav"
    replacement = separators / "Separator-90.wav"
    current.write_bytes(b"current")
    replacement.write_bytes(b"replacement")
    monkeypatch.setattr(crate_export, "SEPARATOR_DIRECTORY", separators)
    playlist = playlists / "Set.m3u8"
    playlist.write_text(f"#EXTM3U\n{current}\n", encoding="utf-8")
    (crates / "Set.json").write_text(json.dumps({"format": 1, "name": "Set", "tracks": [{
        "track_id": "228753448", "file_path": str(current), "separator_type": "generic",
    }]}))
    locations = {
        "228753448": {"id": "228753448", "file_path": str(current)},
        "118082420": {"id": "118082420", "file_path": str(replacement)},
    }

    async def resolve_tracks(**selector):
        return [locations[track_id] for track_id in selector["track_ids"]]

    result = asyncio.run(replace_crate_separator(
        "Set", "228753448-1", "90s", resolve_tracks, playlists, crates, playlists,
    ))

    record = json.loads((crates / "Set.json").read_text())["tracks"][0]
    assert record["track_id"] == "118082420"
    assert record["file_path"] == str(replacement)
    assert record["separator_type"] == "90s"
    assert playlist.read_text().splitlines() == ["#EXTM3U", str(replacement)]
    assert result == {"name": "Set", "track_count": 0, "separator_count": 1, "updated_existing": True}


def _write_crate(tmp_path, track_ids, *, extinf=False):
    playlists = tmp_path / "playlists"
    crates = tmp_path / ".cratebox" / "crates"
    playlists.mkdir()
    crates.mkdir(parents=True)
    audio_paths = []
    lines = ["#EXTM3U\n"]
    tracks = []
    audio_by_id = {}
    for index, track_id in enumerate(track_ids, 1):
        audio = audio_by_id.get(track_id)
        if audio is None:
            audio = tmp_path / f"track-{index}.mp3"
            audio.write_bytes(b"audio")
            audio_by_id[track_id] = audio
        audio_paths.append(audio)
        if extinf:
            lines.append(f"#EXTINF:{index},Track {index}\n")
        lines.append(f"{audio}\n")
        tracks.append({
            "track_id": track_id, "file_path": str(audio),
            "title": f"Track {index}", "rating": 5,
        })
    (playlists / "Set.m3u8").write_text("".join(lines), encoding="utf-8")
    (crates / "Set.json").write_text(json.dumps({"format": 1, "name": "Set", "tracks": tracks}))
    return playlists, crates, audio_paths
