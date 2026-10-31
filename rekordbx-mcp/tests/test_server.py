import json
import shutil
import sys

import pytest
from fastmcp import Client

from rekordbx_mcp.server import build_server
from rekordbx_mcp.snapshot import sha256


@pytest.fixture
def snapshot(encrypted_database):
    directory = encrypted_database.parent
    (directory / "manifest.json").write_text(json.dumps({
        "format": 1, "sha256": sha256(encrypted_database),
    }))
    return directory


async def test_search_uses_snapshot_and_omits_audio_paths(snapshot):
    before = sha256(snapshot / "master.db")
    async with Client(build_server(snapshot)) as client:
        result = await client.call_tool("search_tracks", {"artist": "Daft Punk"})
        tracks = json.loads(result.content[0].text)
        assert tracks[0]["id"] == "1"
        assert tracks[0]["title"] == "One More Time"
        assert tracks[0]["bpm"] == 123.0
        assert "file_path" not in tracks[0]
        details = await client.call_tool("get_track_details", {"track_id": "1"})
        assert json.loads(details.content[0].text)["id"] == "1"
        validated = await client.call_tool("validate_track_ids", {"track_ids": ["1", "999"]})
        result = json.loads(validated.content[0].text)
        assert result["valid"] == ["1"]
        assert result["invalid"] == ["999"]
    assert sha256(snapshot / "master.db") == before


@pytest.mark.parametrize("name,arguments", [
    ("create_playlist", {"name": "Forbidden"}),
    ("delete_playlist", {"playlist_id": "1"}),
    ("add_track_to_playlist", {"playlist_id": "1", "track_id": "1"}),
    ("add_tracks_to_playlist", {"playlist_id": "1", "track_ids": ["1"]}),
    ("remove_track_from_playlist", {"playlist_id": "1", "track_id": "1"}),
    ("import_track", {"path": "/private/original/music/track.mp3"}),
    ("import_tracks", {"paths": ["/private/original"]}),
    ("remove_broken_tracks", {"track_ids": ["1"]}),
    ("cleanup_orphaned_playlist_entries", {}),
    ("connect_database", {"database_path": "/private/original"}),
    ("unexpected_future_tool", {}),
])
async def test_forbidden_tool_cannot_be_called_directly(snapshot, name, arguments):
    async with Client(build_server(snapshot)) as client:
        assert name not in {tool.name for tool in await client.list_tools()}
        with pytest.raises(Exception, match="Unknown tool|not found"):
            await client.call_tool(name, arguments)


async def test_reconnect_never_accepts_another_database(snapshot, tmp_path):
    from rekordbx_mcp.database import SnapshotDatabase
    database = SnapshotDatabase(snapshot)
    await database.connect()
    assert database.db.get_content(ID="1").Title == "One More Time"
    await database.disconnect()
    with pytest.raises(PermissionError):
        await database.connect(tmp_path)
    await database.connect()
    assert database.db.get_content(ID="1").Title == "One More Time"
    await database.disconnect()


async def test_real_mcp_stdio_through_snapshot_launcher(snapshot, monkeypatch):
    from fastmcp.client.transports import StdioTransport
    # Test worker startup independently of host process-list permissions.
    # The startup tests separately exercise the closed-Rekordbox guard.
    monkeypatch.setattr("rekordbx_mcp.snapshot.require_rekordbox_closed", lambda: None)
    from rekordbx_mcp.snapshot import create_snapshot
    source = snapshot / "original" / "master.db"
    source.parent.mkdir()
    shutil.copyfile(snapshot / "master.db", source)
    destination = snapshot / "startup-copies"
    before = sha256(source)
    copied = create_snapshot(source, destination)
    transport = StdioTransport(
        command=sys.executable,
        args=[
            "-m", "rekordbx_mcp.cli", "serve", "--snapshot", str(copied),
        ],
    )
    async with Client(transport, timeout=30) as client:
        tools = {tool.name for tool in await client.list_tools()}
        assert "search_tracks" in tools
        assert "create_playlist" not in tools
        result = await client.call_tool("search_tracks", {"artist": "Daft Punk"})
        assert json.loads(result.content[0].text)[0]["id"] == "1"
    assert sha256(source) == before
    copies = list(destination.glob("*/master.db"))
    assert len(copies) == 1
    assert sha256(copies[0]) == before
    assert copies[0].stat().st_mode & 0o222 == 0
