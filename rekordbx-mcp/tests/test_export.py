import json
from pathlib import Path

import pytest

from rekordbx_mcp.database import SnapshotDatabase
from rekordbx_mcp.snapshot import sha256


@pytest.fixture
async def collection(playable_snapshot):
    database = SnapshotDatabase(playable_snapshot)
    await database.connect()
    try:
        yield database.db
    finally:
        await database.disconnect()


def test_export_preserves_order_unicode_and_inputs(collection, playable_snapshot):
    from rekordbx_mcp.export import export_playlist
    output = playable_snapshot / "output"
    originals = [playable_snapshot / "master.db", *sorted((playable_snapshot / "music").iterdir())]
    before = [sha256(path) for path in originals]
    result = export_playlist(collection, "Été house", ["2", "1", "2"], output)
    playlist = Path(result["playlist_path"])
    assert playlist.parent == output.parent / "playlists"
    assert playlist.suffix == ".m3u8"
    assert result["revision_name"] == "Été house-v001"
    assert playlist.read_text(encoding="utf-8").splitlines() == [
        "#EXTM3U", str(playable_snapshot / "music/Second track.mp3"),
        str(playable_snapshot / "music/Été #1.mp3"),
        str(playable_snapshot / "music/Second track.mp3"),
    ]
    plan = json.loads(Path(result["plan_path"]).read_text(encoding="utf-8"))
    assert plan["name"] == "Été house-v001"
    assert plan["revision_of"] == "Été house"
    assert plan["track_ids"] == ["2", "1", "2"]
    assert result["track_count"] == 3
    assert "music/" not in json.dumps(result)
    assert "music/" not in json.dumps(plan)
    assert [sha256(path) for path in originals] == before


@pytest.mark.parametrize("track_ids,reason", [
    ([], "at least one"),
    ([""], "string track IDs"),
    ([None], "string track IDs"),
    (["/private/music/private-input-track.mp3"], "string track IDs"),
    (["1"] * 1001, "1000"),
    (["1", "999"], "999"),
    (["1", "3"], "3"),
    (["1", "4"], "4"),
    (["1", "5"], "5"),
    (["1", "6"], "6"),
    (["1", "7"], "7"),
])
def test_invalid_selections_fail_without_partial_export(collection, playable_snapshot, track_ids, reason):
    from rekordbx_mcp.export import export_playlist
    output = playable_snapshot / "output"
    with pytest.raises(ValueError, match=reason) as error:
        export_playlist(collection, "House", track_ids, output)
    assert str(playable_snapshot / "music") not in str(error.value)
    assert not output.exists() or not list(output.iterdir())


@pytest.mark.parametrize("name", ["", "  ", "..", "../escape", "/tmp/escape", "a/b", "a\\b", "bad\nname", "bad\x00name", "a" * 201])
def test_unsafe_names_never_write(collection, playable_snapshot, name):
    from rekordbx_mcp.export import export_playlist
    output = playable_snapshot / "output"
    with pytest.raises(ValueError):
        export_playlist(collection, name, ["1"], output)
    assert not output.exists()


@pytest.mark.parametrize("existing", ["House.m3u8", "House.json"])
def test_export_never_overwrites_or_leaves_partial_files(collection, playable_snapshot, existing):
    from rekordbx_mcp.export import export_playlist
    output = playable_snapshot / "output"
    output.mkdir()
    (output / existing).write_text("keep me")
    with pytest.raises(FileExistsError):
        export_playlist(collection, "House", ["1"], output)
    assert (output / existing).read_text() == "keep me"
    assert {path.name for path in output.iterdir()} == {existing}


def test_symlink_output_cannot_redirect_writes_to_originals(collection, playable_snapshot):
    from rekordbx_mcp.export import export_playlist
    music = playable_snapshot / "music"
    output = playable_snapshot / "output"
    output.symlink_to(music, target_is_directory=True)
    before = {path.name: sha256(path) for path in music.iterdir()}
    with pytest.raises(ValueError, match="symlink"):
        export_playlist(collection, "House", ["1"], output)
    assert {path.name: sha256(path) for path in music.iterdir()} == before


def test_existing_symlink_file_is_not_followed(collection, playable_snapshot):
    from rekordbx_mcp.export import export_playlist
    output = playable_snapshot / "output"
    output.mkdir()
    audio = playable_snapshot / "music/Été #1.mp3"
    before = sha256(audio)
    (output / "House.m3u8").symlink_to(audio)
    with pytest.raises(FileExistsError):
        export_playlist(collection, "House", ["1"], output)
    assert sha256(audio) == before


def test_write_failure_removes_incomplete_artifacts(collection, playable_snapshot, monkeypatch):
    from rekordbx_mcp.export import export_playlist
    output = playable_snapshot / "output"

    def disk_failure(_fd):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr("rekordbx_mcp.export.os.fsync", disk_failure)
    with pytest.raises(OSError, match="synthetic disk failure"):
        export_playlist(collection, "House", ["1"], output)
    assert list(output.iterdir()) == []


def test_file_locations_resolve_to_ids_and_preserve_order(collection, playable_snapshot):
    from rekordbx_mcp.export import export_playlist
    output = playable_snapshot / "output"
    audio = [playable_snapshot / "music/Second track.mp3", playable_snapshot / "music/Été #1.mp3"]
    originals = [playable_snapshot / "master.db", *audio]
    before = [sha256(path) for path in originals]
    locations = [str(audio[0]), str(audio[1]), str(audio[0])]
    result = export_playlist(collection, "From locations", None, output, file_paths=locations)
    playlist = Path(result["playlist_path"])
    assert playlist.parent == output.parent / "playlists"
    assert playlist.read_text(encoding="utf-8").splitlines() == ["#EXTM3U", *locations]
    plan = json.loads(Path(result["plan_path"]).read_text(encoding="utf-8"))
    assert plan["track_ids"] == ["2", "1", "2"]
    assert result["track_count"] == 3
    assert str(playable_snapshot / "music") not in json.dumps(result)
    assert str(playable_snapshot / "music") not in json.dumps(plan)
    assert [sha256(path) for path in originals] == before


@pytest.mark.parametrize("filename", ["Not in collection.mp3", "Duplicate.mp3", "Deleted.mp3", "missing.mp3"])
def test_invalid_file_locations_fail_without_echoing_paths(collection, playable_snapshot, filename):
    from rekordbx_mcp.export import export_playlist
    output = playable_snapshot / "output"
    locations = [str(playable_snapshot / "music/Second track.mp3"), str(playable_snapshot / "music" / filename)]
    with pytest.raises(ValueError) as error:
        export_playlist(collection, "Invalid location", None, output, file_paths=locations)
    assert str(playable_snapshot / "music") not in str(error.value)
    assert not output.exists()


@pytest.mark.parametrize("locations", [[], [None], [""], ["relative.mp3"], ["file:///private/music/test.mp3"], ["/private/music/bad\nfile.mp3"], ["/private/music/track.mp3"] * 1001])
def test_invalid_location_inputs_never_write(collection, playable_snapshot, locations):
    from rekordbx_mcp.export import export_playlist
    output = playable_snapshot / "output"
    with pytest.raises(ValueError):
        export_playlist(collection, "Bad input", None, output, file_paths=locations)
    assert not output.exists()


@pytest.mark.parametrize("ids,locations", [(None, None), (["1"], []), ([], []), ([], None)])
def test_selection_requires_exactly_one_nonempty_input(collection, playable_snapshot, ids, locations):
    from rekordbx_mcp.export import export_playlist
    output = playable_snapshot / "output"
    with pytest.raises(ValueError):
        export_playlist(collection, "Bad selection", ids, output, file_paths=locations)
    assert not output.exists()
