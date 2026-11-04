"""Reuse upstream reading tools behind an independent, deny-by-default registry."""

import argparse
import asyncio
import re
import unicodedata
import sys
from contextlib import asynccontextmanager
from difflib import SequenceMatcher
from functools import wraps
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware
from loguru import logger
from pydantic import BaseModel, ValidationError
from rekordbox_mcp import server as upstream
from pyrekordbox.masterdb.models import DjmdPlaylist, DjmdSongPlaylist
from sqlalchemy import func

from .database import SnapshotDatabase, content_by_ids
from .export import OUTPUT_DIRECTORY, PLAYLISTS_DIRECTORY, export_playlist as write_playlist
from .sockseek import create_sockseek_list as write_sockseek_list
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
_MATCH_TRANSLITERATION = str.maketrans({
    "æ": "ae", "œ": "oe", "ø": "o", "ł": "l", "đ": "d",
    "ð": "d", "þ": "th", "ħ": "h", "ı": "i",
})
_ARTIST_SEPARATOR = re.compile(r"\s*(?:[,;&]|\b(?:feat(?:uring)?|ft)\.?|\bx\b)\s*", re.I)
_TITLE_VERSION_MARKERS = {
    "acapella", "club", "clean", "dirty", "edit", "extended", "intro",
    "instrumental", "live", "mashup", "mix", "outro", "radio", "remix",
    "transition", "version", "vip",
}
_TITLE_VERSION_SUFFIXES = (
    "extended remix", "extended mix", "radio edit", "intro edit", "outro edit",
    "quick edit", "short edit", "extended", "instrumental", "acapella",
    "transition", "mashup", "bootleg", "rework", "remix", "version", "clean",
    "dirty", "radio", "intro", "outro", "edit", "mix", "club", "live", "vip",
)


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
    cue_count: int = 0
    playlist_count: int = 0


class CrateDeckLookupTrack(LookupTrack):
    file_path: str


class TrackLocation(BaseModel):
    track_id: str
    file_path: str


class PlaylistSeparator(BaseModel):
    type: Literal["generic", "90s", "R&B", "Ambi", "Salsa", "Party", "Dance"]
    before_track: int


class SockseekTrack(BaseModel):
    artist: str
    title: str


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
    value = value.casefold().translate(_MATCH_TRANSLITERATION)
    decomposed = unicodedata.normalize("NFKD", value)
    unaccented = "".join(char for char in decomposed if not unicodedata.combining(char))
    words = "".join(char if char.isalnum() else " " for char in unaccented)
    return " ".join(words.split())


def artist_credits(value: str) -> set[str]:
    return {
        normalized
        for credit in _ARTIST_SEPARATOR.split(value)
        if (normalized := normalize_match_text(credit))
    }


def normalize_track_title(value: str) -> str:
    original = normalize_match_text(value)
    while match := re.search(r"\s*[\[(]([^\])]+)[\])]\s*$", value):
        suffix = normalize_match_text(match.group(1))
        if not _TITLE_VERSION_MARKERS.intersection(suffix.split()):
            break
        value = value[:match.start()]

    normalized = normalize_match_text(value)
    while normalized:
        suffix = next(
            (item for item in _TITLE_VERSION_SUFFIXES if normalized.endswith(f" {item}")),
            None,
        )
        if suffix is None:
            break
        normalized = normalized[: -(len(suffix) + 1)]
    return normalized or original


def similarity(left: str, right: str) -> float:
    normalized_left = normalize_match_text(left)
    normalized_right = normalize_match_text(right)
    if not normalized_left or not normalized_right:
        return 0.0
    sequence_score = SequenceMatcher(None, normalized_left, normalized_right).ratio()
    left_words, right_words = set(normalized_left.split()), set(normalized_right.split())
    token_score = 2 * len(left_words & right_words) / (len(left_words) + len(right_words))
    return max(sequence_score, token_score)


def order_match_candidates(candidates: list[tuple[float, dict]]) -> list[tuple[float, dict]]:
    groups: dict[tuple[int, float, int, int], list[tuple[float, dict]]] = {}
    for score, candidate in candidates:
        group = (
            int(candidate.pop("_exact_title", False)),
            score,
            int(candidate.get("rating") or 0),
            int(candidate.get("play_count") or 0),
        )
        groups.setdefault(group, []).append((score, candidate))

    ordered = []
    for group in sorted(groups, reverse=True):
        matches = groups[group]
        matches.sort(key=lambda item: item[0], reverse=True)
        # Missing metadata does not count as lower quality; compare a field only
        # when every candidate at this rating/play-count tier has it.
        for field in ("bit_depth", "sample_rate", "bitrate"):
            if all(int(candidate.get(field) or 0) > 0 for _, candidate in matches):
                matches.sort(key=lambda item: int(item[1][field]), reverse=True)
        ordered.extend(matches)
    return ordered


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
                result = await original(*args, **kwargs)
                if tool_name == "get_playlists":
                    def playlist_sequences():
                        return {
                            str(playlist.ID): int(getattr(playlist, "Seq", 0) or 0)
                            for playlist in database.db.get_playlist()
                        }

                    sequences = await asyncio.to_thread(playlist_sequences)
                    result = [
                        {**playlist, "sequence": sequences.get(str(playlist.get("id") or ""), 0)}
                        for playlist in result
                    ]
                return redact_paths(result)
        return call

    for name in READ_TOOLS:
        upstream_tool = getattr(upstream, name)
        original = getattr(upstream_tool, "fn", upstream_tool)
        server.tool(
            name=name, annotations={"readOnlyHint": True, "destructiveHint": False},
        )(wrap(original, name))

    async def rank_similar_tracks(artist: str, title: str, limit: int):
        artist = artist.strip()
        title = title.strip()
        if not artist or not title:
            raise ToolError("Artist and title are required for collection lookup.")
        if not 1 <= limit <= 50:
            raise ToolError("Limit must be between 1 and 50.")

        async with _upstream_lock:
            upstream.db = database
            upstream._db_initialized = True
            upstream.ensure_database_connected = ensure_connected
            try:
                await ensure_connected()

                def ranked_candidates():
                    ranked = []
                    source_artists = artist_credits(artist)
                    for content in database._get_active_content():
                        candidate_artist = str(getattr(content, "ArtistName", "") or "")
                        candidate_artists = artist_credits(candidate_artist)
                        shared_artists = source_artists & candidate_artists
                        if not shared_artists:
                            continue
                        artist_score = len(shared_artists) / min(
                            len(source_artists), len(candidate_artists),
                        )
                        candidate = database._content_to_track(content).model_dump()
                        candidate["_content"] = content
                        candidate["file_path"] = str(getattr(content, "FolderPath", "") or "")
                        candidate["bit_depth"] = int(getattr(content, "BitDepth", 0) or 0)
                        candidate_title = normalize_track_title(str(candidate.get("title") or ""))
                        source_title = normalize_track_title(title)
                        candidate["_exact_title"] = (
                            source_title == candidate_title
                        )
                        score = 0.35 * artist_score + 0.65 * similarity(source_title, candidate_title)
                        ranked.append((score, candidate))
                    selected = order_match_candidates(ranked)[:limit]
                    track_ids = [str(candidate.get("id") or "") for _, candidate in selected]
                    playlist_counts = dict(
                        database.db.session.query(
                            DjmdSongPlaylist.ContentID,
                            func.count(func.distinct(DjmdSongPlaylist.PlaylistID)),
                        )
                        .join(DjmdPlaylist, DjmdPlaylist.ID == DjmdSongPlaylist.PlaylistID)
                        .filter(
                            DjmdSongPlaylist.ContentID.in_(track_ids),
                            DjmdSongPlaylist.rb_local_deleted == 0,
                            DjmdPlaylist.rb_local_deleted == 0,
                        )
                        .group_by(DjmdSongPlaylist.ContentID)
                        .all()
                    )
                    for _, candidate in selected:
                        content = candidate.pop("_content")
                        candidate["cue_count"] = sum(
                            not getattr(cue, "rb_local_deleted", 0)
                            for cue in (getattr(content, "Cues", None) or [])
                        )
                        candidate["playlist_count"] = playlist_counts.get(
                            str(candidate.get("id") or ""), 0,
                        )
                    return selected

                ranked = await asyncio.to_thread(ranked_candidates)
            except Exception:
                logger.exception("Rekordbox collection lookup failed")
                raise ToolError(
                    "Collection lookup failed; check the local server logs."
                ) from None

        return ranked

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def lookup_similar_tracks(
        artist: str, title: str, limit: int = 50,
    ) -> list[LookupTrack]:
        """Find normalized artist/title matches, ranked by exact title, similarity, rating, plays, and quality."""
        ranked = await rank_similar_tracks(artist, title, limit)
        return [LookupTrack(
            id=str(candidate.get("id") or ""),
            title=str(candidate.get("title") or ""),
            artist=str(candidate.get("artist") or ""),
            album=str(candidate.get("album") or ""),
            duration=candidate.get("length") or candidate.get("duration") or 0,
            bpm=candidate.get("bpm") or 0,
            key=str(candidate.get("key") or ""),
            rating=candidate.get("rating") or 0,
            play_count=candidate.get("play_count") or 0,
            cue_count=candidate.get("cue_count") or 0,
            playlist_count=candidate.get("playlist_count") or 0,
            similarity=round(score * 100, 1),
        ) for score, candidate in ranked]

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def lookup_similar_tracks_for_cratedeck(
        artist: str, title: str, limit: int = 50,
    ) -> list[CrateDeckLookupTrack]:
        """App-only lookup that includes paths for CrateDeck's local API playback."""
        ranked = await rank_similar_tracks(artist, title, limit)
        return [CrateDeckLookupTrack(
            id=str(candidate.get("id") or ""),
            title=str(candidate.get("title") or ""),
            artist=str(candidate.get("artist") or ""),
            album=str(candidate.get("album") or ""),
            duration=candidate.get("length") or candidate.get("duration") or 0,
            bpm=candidate.get("bpm") or 0,
            key=str(candidate.get("key") or ""),
            rating=candidate.get("rating") or 0,
            play_count=candidate.get("play_count") or 0,
            cue_count=candidate.get("cue_count") or 0,
            playlist_count=candidate.get("playlist_count") or 0,
            similarity=round(score * 100, 1),
            file_path=str(candidate.get("file_path") or ""),
        ) for score, candidate in ranked]

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def get_track_locations(track_ids: list[str]) -> list[TrackLocation]:
        """Resolve ordered track IDs to paths for trusted local application APIs."""
        if not track_ids or len(track_ids) > 1000 or any(not item for item in track_ids):
            raise ToolError("Provide between 1 and 1000 track IDs.")
        async with _upstream_lock:
            upstream.db = database
            upstream._db_initialized = True
            upstream.ensure_database_connected = ensure_connected
            try:
                await ensure_connected()

                def resolve_locations():
                    contents = content_by_ids(database.db, track_ids)
                    if any(
                        track_id not in contents
                        or contents[track_id].rb_local_deleted
                        or not contents[track_id].FolderPath
                        for track_id in track_ids
                    ):
                        raise ValueError
                    return [
                        TrackLocation(track_id=track_id, file_path=str(contents[track_id].FolderPath))
                        for track_id in track_ids
                    ]

                return await asyncio.to_thread(resolve_locations)
            except ValueError:
                raise ToolError("One or more tracks are unavailable in the active collection.") from None
            except Exception:
                logger.exception("Track location lookup failed")
                raise ToolError("Track location lookup failed; check the local server logs.") from None

    @server.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False})
    async def create_sockseek_list(name: str, tracks: list[SockseekTrack]) -> dict:
        """Create a Sockseek song-search list and a ready-to-run command.

        Writes a new list under downloads/<name>/. The returned command uses
        repository-relative paths and is for manual execution; this tool never
        runs Sockseek or downloads audio.
        Existing lists are never overwritten.
        """
        try:
            return write_sockseek_list(name, [track.model_dump() for track in tracks])
        except (ValueError, FileExistsError) as error:
            raise ToolError(str(error)) from None
        except OSError:
            logger.exception("Sockseek list creation failed")
            raise ToolError("Cannot write the Sockseek list under downloads/; check permissions.") from None

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
