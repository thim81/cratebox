"""Reuse upstream reading tools behind an independent, deny-by-default registry."""

import argparse
import asyncio
import unicodedata
import sys
from contextlib import asynccontextmanager
from difflib import SequenceMatcher
from functools import wraps
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware
from loguru import logger
from pydantic import BaseModel, ValidationError
from rekordbox_mcp import server as upstream

from .database import SnapshotDatabase
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


class LookupTrack(BaseModel):
    id: str
    title: str
    artist: str
    album: str
    duration: int
    bpm: float
    key: str
    rating: int
    play_count: int
    similarity: float


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


def normalize_match_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    unaccented = "".join(char for char in decomposed if not unicodedata.combining(char))
    words = "".join(char if char.isalnum() else " " for char in unaccented)
    return " ".join(words.split())


def similarity(left: str, right: str) -> float:
    return SequenceMatcher(
        None, normalize_match_text(left), normalize_match_text(right),
    ).ratio()


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
    server.add_middleware(ExportInputPrivacy())

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

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def lookup_similar_tracks(
        artist: str, title: str, limit: int = 10,
    ) -> list[LookupTrack]:
        """Find collection tracks matching an artist and a fuzzy title."""
        artist = artist.strip()
        title = title.strip()
        if not artist or not title:
            raise ToolError("Artist and title are required for collection lookup.")
        if not 1 <= limit <= 10:
            raise ToolError("Limit must be between 1 and 10.")

        async with _upstream_lock:
            upstream.db = database
            upstream._db_initialized = True
            upstream.ensure_database_connected = ensure_connected
            try:
                await ensure_connected()

                def ranked_candidates():
                    ranked = []
                    normalized_artist = normalize_match_text(artist)
                    for content in database._get_active_content():
                        candidate_artist = str(getattr(content, "ArtistName", "") or "")
                        artist_score = similarity(artist, candidate_artist)
                        if not candidate_artist or (
                            normalized_artist not in normalize_match_text(candidate_artist)
                            and artist_score < 0.5
                        ):
                            continue
                        candidate = database._content_to_track(content).model_dump()
                        score = 0.35 * artist_score + 0.65 * similarity(
                            title, str(candidate.get("title") or ""),
                        )
                        ranked.append((score, candidate))
                    return ranked

                ranked = await asyncio.to_thread(ranked_candidates)
            except Exception:
                logger.exception("Rekordbox collection lookup failed")
                raise ToolError(
                    "Collection lookup failed; check the local server logs."
                ) from None

        ranked.sort(key=lambda item: item[0], reverse=True)
        results = []
        for score, candidate in ranked[:limit]:
            results.append(LookupTrack(
                id=str(candidate.get("id") or ""),
                title=str(candidate.get("title") or ""),
                artist=str(candidate.get("artist") or ""),
                album=str(candidate.get("album") or ""),
                duration=candidate.get("length") or candidate.get("duration") or 0,
                bpm=candidate.get("bpm") or 0,
                key=str(candidate.get("key") or ""),
                rating=candidate.get("rating") or 0,
                play_count=candidate.get("play_count") or 0,
                similarity=round(score * 100, 1),
            ))
        return results

    @server.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False})
    async def export_playlist(
        name: str, track_ids: list[str] | None = None,
        file_paths: list[str] | None = None,
        update_existing: bool = False,
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
