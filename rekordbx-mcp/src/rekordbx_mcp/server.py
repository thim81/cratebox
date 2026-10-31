"""Reuse upstream reading tools behind an independent, deny-by-default registry."""

import argparse
import asyncio
import sys
from contextlib import asynccontextmanager
from functools import wraps
from pathlib import Path

from fastmcp import FastMCP
from loguru import logger
from rekordbox_mcp import server as upstream

from .database import SnapshotDatabase
from .snapshot import verify_snapshot


READ_TOOLS = (
    "search_tracks", "get_track_details", "get_tracks_by_key",
    "get_tracks_by_bpm_range", "get_most_played_tracks", "get_top_rated_tracks",
    "get_unplayed_tracks", "search_tracks_by_filename", "analyze_library",
    "validate_track_ids", "get_playlists", "get_playlist_tracks",
    "get_library_stats", "get_history_sessions", "get_session_tracks",
    "get_recent_sessions", "get_history_stats", "search_history_sessions",
)
_upstream_lock = asyncio.Lock()


def redact_paths(value):
    if isinstance(value, dict):
        return {
            key: redact_paths(item) for key, item in value.items()
            if key not in ("file_path", "database_path")
        }
    if isinstance(value, list):
        return [redact_paths(item) for item in value]
    return value


def build_server(snapshot: Path) -> FastMCP:
    verify_snapshot(snapshot)
    database = SnapshotDatabase(snapshot)

    async def ensure_connected():
        if not await database.is_connected():
            await database.connect()

    @asynccontextmanager
    async def lifespan(_server):
        try:
            yield {}
        finally:
            await database.disconnect()

    server = FastMCP("Rekordbox snapshot (read-only)", lifespan=lifespan)

    def wrap(original):
        @wraps(original)
        async def call(*args, **kwargs):
            # Upstream's ORM session and module globals are shared. Serialize
            # requests, bind our snapshot and replace every lazy reconnect path.
            async with _upstream_lock:
                upstream.db = database
                upstream._db_initialized = True
                upstream.ensure_database_connected = ensure_connected
                await ensure_connected()
                return redact_paths(await original(*args, **kwargs))
        return call

    for name in READ_TOOLS:
        original = getattr(upstream, name).fn
        server.tool(
            name=name, annotations={"readOnlyHint": True, "destructiveHint": False},
        )(wrap(original))

    @server.resource("snapshot://status")
    def status() -> str:
        return (snapshot / "manifest.json").read_text()

    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    build_server(args.snapshot).run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
