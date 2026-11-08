from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_history_mcp_tools_forward_arguments_and_return_results(monkeypatch):
    from api import app
    from api.collection import collection_mcp

    calls = []

    async def call_tool(name, arguments=None):
        calls.append((name, arguments))
        return SimpleNamespace(
            is_error=False,
            structured_content={"result": [{"id": "session-1"}]},
            data=None,
            content=[],
        )

    monkeypatch.setattr(collection_mcp, "call_tool", call_tool)

    tools = await app.mcp.list_tools()
    sessions = await app.get_history_sessions(include_folders=True, limit=12)
    tracks = await app.get_session_tracks(session_id="session-1")

    assert {tool.name for tool in tools} >= {"get_history_sessions", "get_session_tracks"}
    assert sessions == [{"id": "session-1"}]
    assert tracks == [{"id": "session-1"}]
    assert calls == [
        ("get_history_sessions", {"include_folders": True, "limit": 12}),
        ("get_session_tracks", {"session_id": "session-1"}),
    ]
