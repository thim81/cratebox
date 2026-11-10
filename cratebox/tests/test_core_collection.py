import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import collection


def test_collection_client_serializes_calls_and_reuses_connection(tmp_path, monkeypatch):
    entered = []

    class FakeTool:
        def __init__(self, name):
            self.name = name

    class FakeClient:
        connected = True

        def __init__(self, transport, **kwargs):
            self.transport = transport
            self.calls = 0

        async def __aenter__(self):
            return self

        async def list_tools(self):
            return [FakeTool(name) for name in (
                "get_collection_tracks", "get_track_details", "get_playlists",
                "get_playlist_tracks",
            )]

        def is_connected(self):
            return self.connected

        async def call_tool(self, name, arguments):
            self.calls += 1
            entered.append((name, arguments, self.calls))
            await asyncio.sleep(0)
            return {"result": self.calls}

        async def close(self):
            self.connected = False

    class FakeTransport:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(collection, "Client", FakeClient)
    monkeypatch.setattr(collection, "StdioTransport", FakeTransport)
    client = collection.CollectionClient(tmp_path)

    async def run():
        results = await asyncio.gather(
            client.call_tool("get_collection_tracks", {"offset": 0}),
            client.call_tool("get_collection_tracks", {"offset": 1}),
        )
        await client.close()
        return results

    results = asyncio.run(run())

    assert results == [{"result": 1}, {"result": 2}]
    assert [call[1] for call in entered] == [{"offset": 0}, {"offset": 1}]
    assert client.state == "idle"
    assert client.client is None


def test_tool_rejection_does_not_drop_session_or_retry(tmp_path):
    from fastmcp.exceptions import ToolError
    class RejectedClient:
        calls = 0
        closed = False
        async def call_tool(self, *_):
            self.calls += 1
            raise ToolError('Database transaction sidecar exists; close Rekordbox cleanly.')
        async def close(self):
            self.closed = True
    client = collection.CollectionClient(tmp_path)
    worker = RejectedClient()
    client.client = worker
    async def connect():
        return worker
    client.connect = connect
    async def run():
        try:
            await client.call_tool('edit_playlist', {'action':'move'})
        except ToolError:
            pass
    asyncio.run(run())
    assert worker.calls == 1
    assert not worker.closed
    assert client.client is worker
