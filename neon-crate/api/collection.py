"""Rekordbox collection connection and lookup endpoints."""

import asyncio
from contextlib import suppress
import json
import logging
from pathlib import Path

import mutagen
from fastapi import APIRouter, HTTPException
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from pydantic import BaseModel

from .config import REPO_ROOT

router = APIRouter()
logger = logging.getLogger(__name__)

class CollectionLookup(BaseModel):
    artist: str | None = None
    title: str | None = None
    track_id: str | None = None

class CollectionMcp:
    def __init__(self):
        self.state = "idle"
        self.message = None
        self.client = None
        self.lock = asyncio.Lock()
        self.project = REPO_ROOT / "rekordbx-mcp"
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
                required_tools = {
                    "lookup_similar_tracks_for_cratedeck", "get_track_details",
                    "get_playlists", "get_playlist_tracks", "get_track_locations",
                    "export_playlist",
                }
                if not required_tools <= tool_names:
                    raise RuntimeError("A required Rekordbox collection tool is unavailable.")
                self.client = client
                self.state = "connected"
                return client
            except Exception:
                logger.exception("Failed to start the Rekordbox collection MCP")
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

@router.get("/api/collection/status")
async def collection_status():
    return await collection_mcp.status()

@router.post("/api/collection/lookup")
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
        public_matches = []
        for match in matches:
            if not isinstance(match, dict):
                raise ValueError("Unexpected collection lookup response.")
            public_match = dict(match)
            raw_path = public_match.pop("file_path", None)
            match_id = str(public_match.get("id") or "")
            public_match["cue_count"] = int(public_match.get("cue_count") or 0)
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

