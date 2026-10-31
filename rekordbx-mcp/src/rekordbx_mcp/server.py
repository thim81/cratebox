"""Reuse upstream reading tools behind an independent, deny-by-default registry."""

import argparse
import asyncio
import sys
from contextlib import asynccontextmanager
from functools import wraps
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from loguru import logger
from rekordbox_mcp import server as upstream

from .database import SnapshotDatabase
from .export import OUTPUT_DIRECTORY, export_playlist as write_playlist
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


def build_server(snapshot: Path, *, output_directory: Path = OUTPUT_DIRECTORY) -> FastMCP:
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

    @server.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False})
    async def export_playlist(name: str, track_ids: list[str]) -> dict:
        """Export ordered existing track IDs to new M3U8 and JSON files in output/.

        Use a filename-safe name without an extension. Preserves order and repeats.
        Rejects unknown/deleted IDs, missing audio and existing output filenames.
        Returns artifact paths only; audio paths stay local in the M3U8 file.
        Creates external files only; never imports or edits Rekordbox data.
        """
        async with _upstream_lock:
            await ensure_connected()
            try:
                return write_playlist(database.db, name, track_ids, output_directory)
            except ValueError as error:
                raise ToolError(str(error)) from None
            except FileExistsError:
                raise ToolError("Export files already exist; choose a different playlist name.") from None
            except OSError:
                raise ToolError("Cannot write export files; check the local output directory and permissions.") from None

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
