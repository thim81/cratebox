"""Reuse upstream reading tools behind an independent, deny-by-default registry."""

import argparse
import asyncio
import sys
from contextlib import asynccontextmanager, suppress
from functools import wraps
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from typing import Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware
from loguru import logger
from pydantic import BaseModel, ValidationError
from rekordbox_mcp import database as upstream_database
from rekordbox_mcp import server as upstream
from pyrekordbox.masterdb.models import DjmdCue, DjmdPlaylist, DjmdSongPlaylist
from sqlalchemy import func

from .database import SnapshotDatabase, content_by_ids
from .export import OUTPUT_DIRECTORY, PLAYLISTS_DIRECTORY, export_playlist as write_playlist
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
_database_thread_lock = Lock()


async def _serialized_database_to_thread(function, /, *args, **kwargs):
    def run():
        with _database_thread_lock:
            return function(*args, **kwargs)

    return await asyncio.to_thread(run)


# Upstream database methods use asyncio.to_thread internally, including close().
# Serialize those calls because SnapshotMasterDatabase uses one StaticPool connection.
upstream_database.asyncio = SimpleNamespace(to_thread=_serialized_database_to_thread)
class PlaylistSeparator(BaseModel):
    type: Literal["generic", "90s", "R&B", "Ambi", "Salsa", "Party", "Dance"]
    before_track: int


class ExportInputPrivacy(Middleware):
    async def on_call_tool(self, context, call_next):
        try:
            return await call_next(context)
        except ValidationError:
            if context.message.name != "export_playlist":
                raise
            # Framework validation errors otherwise echo supplied file locations.
            raise ToolError(
                "Invalid export arguments; provide a name and exactly one list: track_ids or file_paths."
            ) from None


def redact_paths(value):
    if isinstance(value, dict):
        return {
            key: redact_paths(item) for key, item in value.items()
            if key not in ("file_path", "database_path")
        }
    if isinstance(value, list):
        return [redact_paths(item) for item in value]
    return value


def build_server(
    snapshot: Path, *, output_directory: Path = OUTPUT_DIRECTORY,
    playlists_directory: Path | None = None,
) -> FastMCP:
    if playlists_directory is None:
        playlists_directory = (
            PLAYLISTS_DIRECTORY if Path(output_directory) == OUTPUT_DIRECTORY
            else Path(output_directory).parent / "playlists"
        )
    verify_snapshot(snapshot)
    database = SnapshotDatabase(snapshot)

    async def complete_before_cancellation(awaitable):
        task = asyncio.create_task(awaitable)
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            with suppress(asyncio.CancelledError, Exception):
                await asyncio.shield(task)
            raise

    async def run_database_operation(function):
        return await complete_before_cancellation(_serialized_database_to_thread(function))

    async def ensure_connected():
        if not await database.is_connected():
            await database.connect()

    @asynccontextmanager
    async def lifespan(_server):
        try:
            yield {}
        finally:
            async with _upstream_lock:
                await database.disconnect()

    server = FastMCP("Rekordbox snapshot (read-only)", lifespan=lifespan)
    server.add_middleware(ExportInputPrivacy())

    def wrap(original, tool_name: str):
        @wraps(original)
        async def call(*args, **kwargs):
            # Upstream's ORM session and module globals are shared. Serialize
            # requests, bind our snapshot and replace every lazy reconnect path.
            async with _upstream_lock:
                upstream.db = database
                upstream._db_initialized = True
                upstream.ensure_database_connected = ensure_connected
                await ensure_connected()
                result = await complete_before_cancellation(original(*args, **kwargs))
                if tool_name == "get_playlists":
                    def playlist_sequences():
                        return {
                            str(playlist.ID): int(getattr(playlist, "Seq", 0) or 0)
                            for playlist in database.db.get_playlist()
                        }

                    sequences = await run_database_operation(playlist_sequences)
                    result = [
                        {**playlist, "sequence": sequences.get(str(playlist.get("id") or ""), 0)}
                        for playlist in result
                    ]
                elif tool_name == "get_playlist_tracks" and isinstance(result, list):
                    def add_usage_counts():
                        track_ids = list(dict.fromkeys(
                            str(track.get("id") or "")
                            for track in result
                            if isinstance(track, dict) and track.get("id") is not None
                        ))
                        if not track_ids:
                            return result
                        cue_counts = dict(database.db.session.query(
                            DjmdCue.ContentID, func.count(DjmdCue.ID),
                        ).filter(
                            DjmdCue.ContentID.in_(track_ids),
                            DjmdCue.rb_local_deleted == 0,
                        ).group_by(DjmdCue.ContentID).all())
                        playlist_rows = database.db.session.query(
                            DjmdSongPlaylist.ContentID,
                            DjmdPlaylist.ID,
                            DjmdPlaylist.Name,
                        ).join(
                            DjmdPlaylist, DjmdPlaylist.ID == DjmdSongPlaylist.PlaylistID,
                        ).filter(
                            DjmdSongPlaylist.ContentID.in_(track_ids),
                            DjmdSongPlaylist.rb_local_deleted == 0,
                            DjmdPlaylist.rb_local_deleted == 0,
                        ).distinct().order_by(DjmdPlaylist.Name).all()
                        memberships = {}
                        for content_id, playlist_id, playlist_name in playlist_rows:
                            memberships.setdefault(str(content_id), []).append({
                                "id": str(playlist_id),
                                "name": str(playlist_name or ""),
                            })
                        for track in result:
                            track_id = str(track.get("id") or "")
                            track_playlists = memberships.get(track_id, [])
                            track["cue_count"] = cue_counts.get(track_id, 0)
                            track["playlist_count"] = len(track_playlists)
                            track["playlists"] = track_playlists
                        return result

                    result = await run_database_operation(add_usage_counts)
                return redact_paths(result)
        return call

    for name in READ_TOOLS:
        upstream_tool = getattr(upstream, name)
        original = getattr(upstream_tool, "fn", upstream_tool)
        server.tool(
            name=name, annotations={"readOnlyHint": True, "destructiveHint": False},
        )(wrap(original, name))

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def get_collection_tracks(
        track_ids: list[str] | None = None,
        file_paths: list[str] | None = None,
        offset: int = 0,
        limit: int = 1000,
    ) -> list[dict]:
        """Resolve ordered IDs or exact file locations, or page through active generic collection tracks. Internal consumer contract."""
        if (
            (track_ids is not None and file_paths is not None)
            or ((track_ids is not None or file_paths is not None) and offset != 0)
            or offset < 0 or not 1 <= limit <= 1000
        ):
            raise ToolError("Provide one selector or a valid page (offset >= 0, limit 1–1000).")
        if track_ids is not None and (not track_ids or len(track_ids) > 1000 or any(not isinstance(x, str) or not x for x in track_ids)):
            raise ToolError("Provide 1–1000 nonempty track IDs.")
        if file_paths is not None and (not file_paths or len(file_paths) > 1000 or any(
            not isinstance(x, str) or not Path(x).is_absolute() or any(c in x for c in "\r\n\x00\x85\u2028\u2029")
            for x in file_paths
        )):
            raise ToolError("Provide 1–1000 absolute file locations.")
        async with _upstream_lock:
            upstream.db = database
            upstream._db_initialized = True
            upstream.ensure_database_connected = ensure_connected
            await ensure_connected()

            def resolve():
                query = database.db.get_content()
                model = query.column_descriptions[0]["entity"]
                query = query.filter(model.rb_local_deleted == 0)
                if track_ids is not None:
                    by_id = content_by_ids(database.db, track_ids)
                    if any(i not in by_id or by_id[i].rb_local_deleted for i in track_ids):
                        raise ValueError
                    rows = [by_id[i] for i in track_ids]
                elif file_paths is not None:
                    rows = []
                    for location in file_paths:
                        matches = query.filter(model.FolderPath == location).all()
                        if len(matches) != 1:
                            raise ValueError
                        rows.append(matches[0])
                else:
                    rows = query.order_by(model.ID).offset(offset).limit(limit).all()
                ids = list(dict.fromkeys(str(row.ID) for row in rows))
                cues = dict(database.db.session.query(DjmdCue.ContentID, func.count(DjmdCue.ID)).filter(
                    DjmdCue.ContentID.in_(ids), DjmdCue.rb_local_deleted == 0,
                ).group_by(DjmdCue.ContentID).all()) if ids else {}
                memberships = {}
                if ids:
                    for content_id, playlist_id, name in database.db.session.query(
                        DjmdSongPlaylist.ContentID, DjmdPlaylist.ID, DjmdPlaylist.Name,
                    ).join(DjmdPlaylist, DjmdPlaylist.ID == DjmdSongPlaylist.PlaylistID).filter(
                        DjmdSongPlaylist.ContentID.in_(ids), DjmdSongPlaylist.rb_local_deleted == 0,
                        DjmdPlaylist.rb_local_deleted == 0,
                    ).distinct().order_by(DjmdPlaylist.Name).all():
                        memberships.setdefault(str(content_id), []).append({"id": str(playlist_id), "name": str(name or "")})
                output = []
                for row in rows:
                    item = database._content_to_track(row).model_dump()
                    key = str(row.ID)
                    item.update(file_path=str(row.FolderPath or ""), bit_depth=int(row.BitDepth or 0),
                                sample_rate=int(row.SampleRate or 0), bitrate=int(row.BitRate or 0),
                                cue_count=cues.get(key, 0), playlists=memberships.get(key, []),
                                playlist_count=len(memberships.get(key, [])))
                    output.append(item)
                return output

            try:
                return await run_database_operation(resolve)
            except ValueError:
                raise ToolError("A selector must resolve to active collection tracks; each file location must match exactly one track.") from None

    @server.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False})
    async def export_playlist(
        name: str, track_ids: list[str] | None = None,
        file_paths: list[str] | None = None,
        update_existing: bool = False,
        separators: list[PlaylistSeparator] | None = None,
    ) -> dict:
        """Export tracks as an M3U8 in playlists/ and matching JSON in output/.

        Use a filename-safe name without an extension. If an export with that
        name already exists, ask whether to update it or create a separate
        playlist with a different name. To update the confirmed existing export,
        call again with update_existing=true. Never update without confirmation.
        Supply exactly one of track_ids or file_paths, with 1–1000 entries.
        File paths must be absolute and match exactly one active snapshot track.
        Rejects unknown/deleted IDs and missing audio. New names never replace files.
        Returns artifact paths only; the JSON plan pairs each ID with its audio path.
        Audio paths are not returned in this tool response.
        Optionally add separators before 1-based track positions; use
        before_track=len(track_ids)+1 to append. Separator types are generic,
        90s, R&B, Ambi, Salsa, Party, and Dance. Each resolves to its fixed
        supplied WAV file and must match exactly one active snapshot track.
        Prefer track_ids to avoid sending audio paths in tool arguments.
        Creates external files only; never imports or edits Rekordbox data.
        """
        async with _upstream_lock:
            try:
                await ensure_connected()
                return write_playlist(
                    database.db, name, track_ids, output_directory,
                    file_paths=file_paths, playlists_directory=playlists_directory,
                    update_existing=update_existing,
                    separators=[item.model_dump() for item in separators] if separators else None,
                )
            except ValueError as error:
                raise ToolError(str(error)) from None
            except FileExistsError as error:
                raise ToolError(str(error)) from None
            except OSError:
                raise ToolError("Cannot write export files; check the local playlists/ and output/ directories and permissions.") from None
            except Exception:
                logger.exception("Playlist export failed")
                raise ToolError("Playlist export failed; check the local server logs.") from None

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
