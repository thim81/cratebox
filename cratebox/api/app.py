"""FastAPI application setup for the local CrateBox API."""

from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import FastMCP

from .collection import collection_mcp, router as collection_router
from .playlists import playlist_revision, router as playlists_router
from .artwork import router as artwork_router
from .streaming import router as streaming_router
from .rekordbox_playlists import router as rekordbox_playlists_router
from .ratings import router as ratings_router

mcp = FastMCP("CrateBox")
mcp_app = mcp.http_app(path="/")

@asynccontextmanager
async def lifespan(_app):
    try:
        async with mcp_app.lifespan(mcp_app):
            yield
    finally:
        await collection_mcp.close()

app = FastAPI(title="CrateBox playlist API", lifespan=lifespan)


@app.middleware("http")
async def bump_playlist_revision_after_rest_write(request, call_next):
    response = await call_next(request)
    path = request.url.path
    playlist_write = (
        (path == "/api/playlists" and request.method == "POST")
        or (path.startswith("/api/playlists/") and path.rsplit("/", 1)[-1] in {
            "tracks", "swap", "reorder", "append", "append-many", "insert-after",
            "separators",
        } and request.method in {"POST", "DELETE"})
        or (path.startswith("/api/playlists/") and path.endswith("/separators/replace") and request.method == "POST")
        or (path.startswith("/api/rekordbox/playlists/") and path.endswith("/copy") and request.method == "POST")
    )
    if playlist_write and response.status_code < 400:
        playlist_revision.mark_written()
    return response

@mcp.tool
async def cratebox_list_playlists():
    """List locally editable CrateBox playlists."""
    from .playlists import list_playlists
    return list_playlists()

@mcp.tool
async def cratebox_get_playlist(playlist_id: str):
    """Get a local playlist and its ordered tracks."""
    from .playlists import get_playlist
    return get_playlist(playlist_id)

@mcp.tool
async def cratebox_create_playlist(name: str):
    """Create an empty local playlist."""
    from .playlists import PlaylistCreate, create_playlist
    result = await create_playlist(PlaylistCreate(name=name))
    playlist_revision.mark_written()
    return result

@mcp.tool
async def cratebox_remove_tracks(playlist_id: str, track_ids: list[str]):
    """Remove selected rows from a local playlist."""
    from .playlists import delete_tracks
    result = await delete_tracks(playlist_id, track_ids)
    playlist_revision.mark_written()
    return result

@mcp.tool
async def cratebox_reorder_tracks(
    playlist_id: str, source_track_ids: list[str], target_track_id: str, before: bool,
):
    """Move ordered rows before or after a target row in a local playlist."""
    from .playlists import PlaylistReorder, reorder_track
    result = await reorder_track(playlist_id, PlaylistReorder(
        source_track_ids=source_track_ids, target_track_id=target_track_id, before=before,
    ))
    playlist_revision.mark_written()
    return result

@mcp.tool
async def lookup_similar_tracks(artist: str = "", title: str = "", limit: int = 50):
    """Find candidate tracks in the protected Rekordbox snapshot."""
    from .collection import CollectionLookup, collection_lookup
    result = await collection_lookup(CollectionLookup(artist=artist, title=title, limit=limit))
    return result["matches"]

@mcp.tool
async def search_tracks(
    query: str = "", artist: str | None = None, title: str | None = None,
    genre: str | None = None, key: str | None = None, bpm_min: float | None = None,
    bpm_max: float | None = None, rating_min: int | None = None, limit: int = 50,
):
    """Search active tracks in the protected Rekordbox snapshot."""
    from .collection import collection_mcp
    result = await collection_mcp.call_tool("search_tracks", {
        "query": query, "artist": artist, "title": title, "genre": genre,
        "key": key, "bpm_min": bpm_min, "bpm_max": bpm_max,
        "rating_min": rating_min, "limit": limit,
    })
    from .rekordbox_playlists import result_value
    return result_value(result)

@mcp.tool
async def get_track_details(track_id: str):
    """Read one track's collection metadata."""
    from .collection import collection_mcp
    from .rekordbox_playlists import result_value
    return result_value(await collection_mcp.call_tool("get_track_details", {"track_id": track_id}))

@mcp.tool
async def get_rekordbox_playlists():
    """Browse read-only Rekordbox playlists and folders."""
    from .rekordbox_playlists import get_rekordbox_playlists as list_records
    return await list_records()

@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
async def get_history_sessions(include_folders: bool = False, limit: int = 100):
    """List Rekordbox DJ history sessions, optionally including folder entries."""
    from .collection import collection_mcp
    from .rekordbox_playlists import result_value
    return result_value(await collection_mcp.call_tool("get_history_sessions", {
        "include_folders": include_folders, "limit": limit,
    }))

@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
async def get_session_tracks(session_id: str):
    """Read tracks and performance context from a Rekordbox history session."""
    from .collection import collection_mcp
    from .rekordbox_playlists import result_value
    return result_value(await collection_mcp.call_tool("get_session_tracks", {
        "session_id": session_id,
    }))

@mcp.tool
async def get_library_stats():
    """Read aggregate statistics from the protected collection snapshot."""
    from .collection import collection_mcp
    from .rekordbox_playlists import result_value
    return result_value(await collection_mcp.call_tool("get_library_stats"))

@mcp.tool
async def cratebox_copy_rekordbox_playlist(playlist_id: str, name: str, update_existing: bool = False):
    """Copy a Rekordbox playlist into CrateBox; confirm before replacing an existing export."""
    from .rekordbox_playlists import CopyPlaylistRequest, copy_rekordbox_playlist
    result = await copy_rekordbox_playlist(playlist_id, CopyPlaylistRequest(
        name=name, update_existing=update_existing,
    ))
    playlist_revision.mark_written()
    return result

@mcp.tool
async def cratebox_append_tracks(playlist_id: str, track_ids: list[str], confirm_update: bool = False):
    """Append collection track IDs to a local playlist; confirm before modifying it."""
    from .rekordbox_playlists import AppendTracksRequest, append_rekordbox_tracks
    result = await append_rekordbox_tracks(playlist_id, AppendTracksRequest(
        track_ids=track_ids, confirm_update=confirm_update,
    ))
    playlist_revision.mark_written()
    return result

@mcp.tool
async def cratebox_insert_track(playlist_id: str, track_id: str, after_track_id: str, confirm_update: bool = False):
    """Insert a collection track after a playlist row; confirm before modifying it."""
    from .rekordbox_playlists import InsertTrackRequest, insert_rekordbox_track
    result = await insert_rekordbox_track(playlist_id, InsertTrackRequest(
        track_id=track_id, after_track_id=after_track_id, confirm_update=confirm_update,
    ))
    playlist_revision.mark_written()
    return result

@mcp.tool
async def cratebox_insert_separator(playlist_id: str, separator_type: str, after_track_id: str, confirm_update: bool = False):
    """Insert a fixed separator track after a playlist row; confirm before modifying it."""
    from .rekordbox_playlists import InsertSeparatorRequest, insert_playlist_separator
    result = await insert_playlist_separator(playlist_id, InsertSeparatorRequest(
        type=separator_type, after_track_id=after_track_id, confirm_update=confirm_update,
    ))
    playlist_revision.mark_written()
    return result

@mcp.tool
async def spotify_tracklist(url: str):
    """Read an ordered artist/title list from a public Spotify playlist URL."""
    from core.spotify import spotify_tracklist as read_tracklist
    try:
        return await asyncio.to_thread(read_tracklist, url)
    except ValueError as error:
        raise ValueError(str(error)) from None

@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False})
async def create_sockseek_list(name: str, tracks: list[dict[str, str]]):
    """Create a Sockseek search list from ordered artist/title pairs."""
    from core.sockseek import create_sockseek_list as write_sockseek_list
    return await asyncio.to_thread(write_sockseek_list, name, tracks)

@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False})
async def export_playlist(
    name: str, track_ids: list[str] | None = None,
    file_paths: list[str] | None = None, update_existing: bool = False,
    separators: list[dict] | None = None,
):
    """Export ordered collection tracks as a local M3U8/JSON playlist pair."""
    from .rekordbox_playlists import export_local_playlist
    from .playlists import playlist_mutation_lock
    async with playlist_mutation_lock(name):
        result = await export_local_playlist(
            name, track_ids=track_ids, file_paths=file_paths,
            update_existing=update_existing, separators=separators,
        )
    playlist_revision.mark_written()
    return result

app.mount("/mcp", mcp_app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
app.include_router(collection_router)
app.include_router(playlists_router)
app.include_router(artwork_router)
app.include_router(streaming_router)
app.include_router(rekordbox_playlists_router)
app.include_router(ratings_router)
