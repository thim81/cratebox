"""Local API for the CrateDeck playlist browser."""

from datetime import date
from pathlib import Path
from contextlib import asynccontextmanager, suppress
import hashlib
import json
from urllib.parse import quote
import os
import tempfile
import asyncio

import mutagen
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from pydantic import BaseModel

DEFAULT_PLAYLIST_DIR = Path(__file__).resolve().parents[1] / "playlists"
PLAN_DIRECTORY = Path(__file__).resolve().parents[1] / "output"
PLAYLIST_DIR = Path(os.environ.get("PLAYLIST_DIR", str(DEFAULT_PLAYLIST_DIR))).expanduser().resolve()


class CollectionLookup(BaseModel):
    artist: str | None = None
    title: str | None = None
    track_id: str | None = None


class PlaylistSwap(BaseModel):
    source_track_id: str
    replacement_track_id: str


class CollectionMcp:
    def __init__(self):
        self.state = "idle"
        self.message = None
        self.client = None
        self.lock = asyncio.Lock()
        self.project = Path(__file__).resolve().parents[1] / "rekordbx-mcp"
        self.track_paths: dict[str, Path] = {}

    async def status(self):
        if self.client:
            try:
                if not await self.client.ping():
                    raise RuntimeError("MCP worker did not respond.")
            except Exception:
                with suppress(Exception):
                    await self.client.close()
                self.client = None
                self.state = "error"
                self.message = "Collection connection was lost. Try Lookup again or restart the local API."
                self.track_paths.clear()
        return {"state": self.state, "message": self.message}

    async def connect(self):
        async with self.lock:
            if self.client:
                return self.client
            self.state = "starting"
            self.message = None
            transport = StdioTransport(
                command="uv",
                args=["run", "--locked", "--offline", "rekordbx-mcp", "start"],
                cwd=str(self.project),
            )
            client = Client(transport, timeout=120, init_timeout=120)
            try:
                await client.__aenter__()
                tool_names = {tool.name for tool in await client.list_tools()}
                if not {"lookup_similar_tracks_for_cratedeck", "get_track_details"} <= tool_names:
                    raise RuntimeError("Lookup tool is unavailable.")
                self.client = client
                self.state = "connected"
                return client
            except Exception:
                with suppress(Exception):
                    await client.close()
                self.state = "error"
                self.message = "Could not connect to the Rekordbox collection. Close Rekordbox and its background agents, then try again."
                self.track_paths.clear()
                raise HTTPException(503, self.message) from None

    async def close(self):
        async with self.lock:
            if self.client:
                with suppress(Exception):
                    await self.client.close()
                self.client = None
            self.track_paths.clear()
            if self.state in ("starting", "connected"):
                self.state = "idle"
            self.message = None


collection_mcp = CollectionMcp()


@asynccontextmanager
async def lifespan(_app):
    try:
        yield
    finally:
        await collection_mcp.close()


app = FastAPI(title="CrateDeck playlist API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.get("/api/collection/status")
async def collection_status():
    return await collection_mcp.status()


@app.post("/api/collection/lookup")
async def collection_lookup(request: CollectionLookup):
    artist = (request.artist or "").strip()
    title = (request.title or "").strip()
    track_id = (request.track_id or "").strip()
    if not track_id and (not artist or not title):
        raise HTTPException(400, "Provide a Rekordbox track ID or both artist and title.")
    client = await collection_mcp.connect()
    try:
        async def result_value(tool_result):
            structured = tool_result.structured_content
            value = structured.get("result") if isinstance(structured, dict) and "result" in structured else structured
            if value is None:
                value = tool_result.data
            if value is None and tool_result.content:
                value = json.loads(tool_result.content[0].text)
            return value

        if track_id:
            details = await client.call_tool("get_track_details", {"track_id": track_id})
            source = await result_value(details)
            if isinstance(source, list):
                source = source[0] if source else None
            if isinstance(source, dict):
                artist = str(source.get("artist") or artist).strip()
                title = str(source.get("title") or title).strip()
            if artist and title:
                result = await client.call_tool(
                    "lookup_similar_tracks_for_cratedeck", {"artist": artist, "title": title},
                )
                matches = await result_value(result)
            elif isinstance(source, dict):
                matches = [{
                    "id": str(source.get("id") or track_id),
                    "title": str(source.get("title") or ""),
                    "artist": str(source.get("artist") or ""),
                    "album": str(source.get("album") or ""),
                    "duration": source.get("duration") or source.get("length") or 0,
                    "bpm": source.get("bpm") or 0,
                    "key": str(source.get("key") or ""),
                    "rating": source.get("rating") or 0,
                    "play_count": source.get("play_count") or 0,
                    "similarity": 100,
                }]
            else:
                matches = []
        else:
            result = await client.call_tool(
                "lookup_similar_tracks_for_cratedeck", {"artist": artist, "title": title},
            )
            matches = await result_value(result)
        if not isinstance(matches, list):
            raise ValueError("Unexpected collection lookup response.")
        collection_mcp.track_paths.clear()
        public_matches = []
        for match in matches:
            if not isinstance(match, dict):
                raise ValueError("Unexpected collection lookup response.")
            public_match = dict(match)
            raw_path = public_match.pop("file_path", None)
            match_id = str(public_match.get("id") or "")
            playable = False
            if (
                match_id and isinstance(raw_path, str) and Path(raw_path).is_absolute()
                and not any(character in raw_path for character in "\r\n\x00\x85\u2028\u2029")
            ):
                audio_path = Path(raw_path)
                if audio_path.is_file():
                    collection_mcp.track_paths[match_id] = audio_path
                    playable = True
                    media = mutagen.File(audio_path, easy=True)
                    bitrate = getattr(getattr(media, "info", None), "bitrate", 0) or 0
                    public_match["quality"] = f"{audio_path.suffix[1:].upper()} {bitrate // 1000}kbps".strip()
            public_match["playable"] = playable
            public_matches.append(public_match)
        collection_mcp.state = "connected"
        collection_mcp.message = None
        return {"matches": public_matches}
    except Exception:
        error_message = "Collection lookup failed."
        if collection_mcp.client:
            try:
                if not await collection_mcp.client.ping():
                    raise RuntimeError("MCP worker did not respond.")
                collection_mcp.state = "connected"
                collection_mcp.message = None
            except Exception:
                with suppress(Exception):
                    await collection_mcp.client.close()
                collection_mcp.client = None
                collection_mcp.state = "error"
                collection_mcp.message = "Collection connection was lost. Try Lookup again or restart the local API."
                error_message = collection_mcp.message
        raise HTTPException(502, error_message) from None


@app.get("/api/collection/stream/{track_id}")
def collection_stream(track_id: str):
    audio_path = collection_mcp.track_paths.get(track_id)
    if audio_path is None or not audio_path.is_file():
        raise HTTPException(404, "Rekordbox track not found in the latest lookup.")
    return FileResponse(audio_path, headers={"Cache-Control": "no-store"})


def playlist_files():
    return sorted(
        (p for p in PLAYLIST_DIR.glob("*.m3u*") if p.is_file() and p.suffix.lower() in {".m3u", ".m3u8"}),
        key=lambda p: (p.stem.casefold(), p.name.casefold()),
    )


def playlist_entry_count(lines: list[str]):
    return sum(1 for line in lines if line.strip() and not line.lstrip().startswith("#"))


def read_plan_ids(path: Path, lines: list[str]):
    plan_path = PLAN_DIRECTORY / f"{path.stem}.json"
    if PLAN_DIRECTORY.is_symlink() or plan_path.is_symlink():
        raise HTTPException(409, "The playlist and its track-ID plan are out of sync")
    if not plan_path.exists():
        return plan_path, None
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if not isinstance(plan, dict):
            raise ValueError
        if "tracks" in plan:
            entries = plan["tracks"]
            if not isinstance(entries, list):
                raise ValueError
            track_ids = [entry.get("track_id") for entry in entries if isinstance(entry, dict)]
            if len(track_ids) != len(entries):
                raise ValueError
            file_paths = [entry.get("file_path") for entry in entries if isinstance(entry, dict)]
            if any(
                not isinstance(item, str) or not Path(item).is_absolute()
                or any(character in item for character in "\r\n\x00\x85\u2028\u2029")
                for item in file_paths
            ):
                raise ValueError
        else:
            track_ids = plan.get("track_ids")
            file_paths = None
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        raise HTTPException(409, "The playlist and its track-ID plan are out of sync") from None
    entry_count = playlist_entry_count(lines)
    if (
        not isinstance(track_ids, list)
        or len(track_ids) != entry_count
        or any(not isinstance(track_id, str) or not track_id for track_id in track_ids)
        or (file_paths is not None and len(file_paths) != entry_count)
    ):
        raise HTTPException(409, "The playlist and its track-ID plan are out of sync")
    if file_paths is not None:
        playlist_paths = [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]
        for playlist_path, plan_path_value in zip(playlist_paths, file_paths, strict=True):
            current_path = Path(playlist_path).expanduser()
            if not current_path.is_absolute():
                current_path = path.parent / current_path
            try:
                paths_match = current_path.resolve() == Path(plan_path_value).resolve()
            except (OSError, RuntimeError, ValueError):
                paths_match = False
            if not paths_match:
                raise HTTPException(409, "The playlist and its track-ID plan are out of sync")
    return plan_path, (track_ids, file_paths)


def playlist_entries(path: Path, lines: list[str], plan: tuple[list[str], list[str] | None] | None):
    path_occurrences = {}
    track_occurrences = {}
    entry_number = 0
    for line_number, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        plan_index = entry_number
        rekordbox_id = plan[0][entry_number] if plan else None
        entry_number += 1
        audio = Path(plan[1][plan_index]) if plan and plan[1] else Path(line).expanduser()
        if not audio.is_absolute():
            audio = path.parent / audio
        audio = audio.resolve()
        if not audio.is_file():
            continue
        audio_key = str(audio)
        if rekordbox_id:
            occurrence = track_occurrences.get(rekordbox_id, 0)
            track_occurrences[rekordbox_id] = occurrence + 1
            row_id = f"{rekordbox_id}-{occurrence + 1}"
        else:
            occurrence = path_occurrences.get(audio_key, 0)
            path_occurrences[audio_key] = occurrence + 1
            digest = hashlib.blake2b(audio_key.encode(), digest_size=8).hexdigest()
            row_id = f"{path.stem}-{digest}-{occurrence}"
        yield line_number, plan_index, audio, row_id, rekordbox_id


def atomic_write(path: Path, content: str):
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
        temporary_path.chmod(path.stat().st_mode)
        os.replace(temporary_path, path)
    except OSError:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
        raise


def parse_playlist(path: Path):
    tracks = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        raise HTTPException(500, f"Could not read playlist {path.name}") from exc

    _, plan = read_plan_ids(path, lines)
    for _, _, audio, track_id, rekordbox_id in playlist_entries(path, lines, plan):
        try:
            media = mutagen.File(audio, easy=True)
        except (OSError, ValueError):
            media = None
        tags = media or {}
        info = getattr(media, "info", None)

        def tag(key, default=""):
            values = tags.get(key, [])
            return str(values[0]) if values else default

        try:
            bpm = int(float(tag("bpm", "0") or 0))
        except (TypeError, ValueError):
            bpm = 0
        bitrate = getattr(info, "bitrate", 0) or 0
        tracks.append({
            "id": track_id,
            "rekordbox_id": rekordbox_id,
            "title": tag("title", audio.stem),
            "artist": tag("artist"),
            "album": tag("album"),
            "duration": round(getattr(info, "length", 0) or 0),
            "rating": 0,
            "bpm": bpm,
            "key": tag("initialkey"),
            "quality": f"{audio.suffix[1:].upper()} {bitrate // 1000}kbps".strip(),
            "url": f"/api/stream?playlist_id={quote(path.stem)}&track_id={quote(track_id)}",
        })
    return tracks


def playlist_summary(path: Path, tracks):
    created = date.fromtimestamp(path.stat().st_ctime).isoformat()
    return {
        "id": path.stem,
        "name": path.stem,
        "trackCount": len(tracks),
        "duration": sum(track["duration"] for track in tracks),
        "created": created,
    }


def find_playlist(playlist_id: str):
    matches = [p for p in playlist_files() if p.stem == playlist_id]
    if not matches:
        raise HTTPException(404, "Playlist not found")
    return matches[0]


@app.get("/api/playlists")
def list_playlists():
    return [playlist_summary(path, parse_playlist(path)) for path in playlist_files()]


@app.get("/api/playlists/{playlist_id}")
def get_playlist(playlist_id: str):
    path = find_playlist(playlist_id)
    tracks = parse_playlist(path)
    return {**playlist_summary(path, tracks), "tracks": tracks}


@app.delete("/api/playlists/{playlist_id}/tracks")
def delete_tracks(playlist_id: str, track_ids: list[str] = Body(..., embed=True)):
    if DEFAULT_PLAYLIST_DIR.is_symlink() or PLAYLIST_DIR != DEFAULT_PLAYLIST_DIR:
        raise HTTPException(403, "Playlist edits are limited to the app's playlists folder")
    if not track_ids or len(track_ids) > 1000 or len(set(track_ids)) != len(track_ids):
        raise HTTPException(400, "Select between 1 and 1000 unique tracks")

    path = find_playlist(playlist_id)
    try:
        with path.open(encoding="utf-8-sig", newline="") as playlist:
            lines = playlist.readlines()
    except (OSError, UnicodeError) as exc:
        raise HTTPException(500, "Could not read playlist") from exc

    plan_path, plan = read_plan_ids(path, lines)
    plan_data = None
    if plan_path.is_file():
        if plan is None or plan_path.is_symlink() or PLAN_DIRECTORY.is_symlink():
            raise HTTPException(409, "The playlist and its track-ID plan are out of sync")
        plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
    entries = {
        track_id: (line_number, plan_index)
        for line_number, plan_index, _, track_id, _ in playlist_entries(path, lines, plan)
    }
    remove_indices = set()
    remove_plan_indices = set()
    for track_id in track_ids:
        if track_id not in entries:
            raise HTTPException(404, "Track not found in playlist")
        index, plan_index = entries[track_id]
        remove_indices.add(index)
        remove_plan_indices.add(plan_index)
        if index and lines[index - 1].lstrip().startswith("#EXTINF:"):
            remove_indices.add(index - 1)

    updated_lines = [line for index, line in enumerate(lines) if index not in remove_indices]
    if plan_data is not None:
        if isinstance(plan_data.get("tracks"), list):
            plan_data["tracks"] = [
                entry for index, entry in enumerate(plan_data["tracks"])
                if index not in remove_plan_indices
            ]
        else:
            plan_data["track_ids"] = [
                track_id for index, track_id in enumerate(plan_data["track_ids"])
                if index not in remove_plan_indices
            ]
    original_text = "".join(lines)
    playlist_updated = False
    try:
        atomic_write(path, "".join(updated_lines))
        playlist_updated = True
        if plan_data is not None:
            plan_text = json.dumps(plan_data, ensure_ascii=False, indent=2) + "\n"
            atomic_write(plan_path, plan_text)
    except OSError as exc:
        if playlist_updated:
            try:
                atomic_write(path, original_text)
            except OSError:
                raise HTTPException(500, "Playlist and track-ID plan may be out of sync") from None
        raise HTTPException(500, "Could not update playlist") from exc
    return {"removed": len(track_ids)}


@app.post("/api/playlists/{playlist_id}/tracks/swap")
def swap_track(playlist_id: str, request: PlaylistSwap):
    if DEFAULT_PLAYLIST_DIR.is_symlink() or PLAYLIST_DIR != DEFAULT_PLAYLIST_DIR:
        raise HTTPException(403, "Playlist edits are limited to the app's playlists folder")
    if not request.source_track_id or not request.replacement_track_id:
        raise HTTPException(400, "Both playlist and replacement track IDs are required")
    replacement_audio = collection_mcp.track_paths.get(request.replacement_track_id)
    if replacement_audio is None or not replacement_audio.is_file():
        raise HTTPException(404, "Replacement track is unavailable; run lookup again")

    path = find_playlist(playlist_id)
    try:
        with path.open(encoding="utf-8-sig", newline="") as playlist:
            lines = playlist.readlines()
    except (OSError, UnicodeError) as exc:
        raise HTTPException(500, "Could not read playlist") from exc

    plan_path, plan = read_plan_ids(path, lines)
    entries = list(playlist_entries(path, lines, plan))
    source = next(
        (entry for entry in entries if entry[3] == request.source_track_id), None,
    )
    if source is None:
        raise HTTPException(404, "Source track not found in playlist")
    line_number, plan_index = source[0], source[1]
    original_text = "".join(lines)
    line_ending = "\r\n" if lines[line_number].endswith("\r\n") else "\n" if lines[line_number].endswith("\n") else ""
    lines[line_number] = f"{replacement_audio}{line_ending}"

    plan_data = None
    if plan_path.is_file():
        if plan is None or plan_path.is_symlink() or PLAN_DIRECTORY.is_symlink():
            raise HTTPException(409, "The playlist and its track-ID plan are out of sync")
        try:
            plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
            if isinstance(plan_data.get("tracks"), list):
                plan_data["tracks"][plan_index]["track_id"] = request.replacement_track_id
                plan_data["tracks"][plan_index]["file_path"] = str(replacement_audio)
            else:
                plan_data["track_ids"][plan_index] = request.replacement_track_id
        except (AttributeError, IndexError, KeyError, TypeError, OSError, UnicodeError, json.JSONDecodeError):
            raise HTTPException(409, "The playlist and its track-ID plan are out of sync") from None

    playlist_updated = False
    try:
        atomic_write(path, "".join(lines))
        playlist_updated = True
        if plan_data is not None:
            atomic_write(plan_path, json.dumps(plan_data, ensure_ascii=False, indent=2) + "\n")
    except OSError as exc:
        if playlist_updated:
            try:
                atomic_write(path, original_text)
            except OSError:
                raise HTTPException(500, "Playlist and track-ID plan may be out of sync") from None
        raise HTTPException(500, "Could not update playlist") from exc

    updated_plan = None
    if plan is not None:
        track_ids = list(plan[0])
        track_ids[plan_index] = request.replacement_track_id
        file_paths = list(plan[1]) if plan[1] is not None else None
        if file_paths is not None:
            file_paths[plan_index] = str(replacement_audio)
        updated_plan = (track_ids, file_paths)
    updated_entries = playlist_entries(path, lines, updated_plan)
    updated_track = next((entry for entry in updated_entries if entry[1] == plan_index), None)
    return {"track_id": updated_track[3] if updated_track else None}


@app.get("/api/stream")
def stream(playlist_id: str, track_id: str):
    path = find_playlist(playlist_id)
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    _, plan = read_plan_ids(path, lines)
    for _, _, audio, registered_id, _ in playlist_entries(path, lines, plan):
        if registered_id == track_id:
            return FileResponse(audio)
    raise HTTPException(404, "Track not found in playlist")
