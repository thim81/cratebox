# CrateDeck local playlist API

The app reads `.m3u` and `.m3u8` playlists through a small local FastAPI server.
In the repository's `playlists/` folder, tracks can be removed or replaced in a playlist;
the audio file is never deleted. Other configured playlist folders remain read-only.

From this folder, run:

```sh
uv --directory ../rekordbx-mcp run --locked --with fastapi --with uvicorn --with mutagen \
  uvicorn --app-dir ../neon-crate --reload-dir ../neon-crate --reload-dir src \
  server:app --port 8000 --reload
```

By default, playlists are read from the repository root `playlists/` folder. To use another folder:

```sh
PLAYLIST_DIR="/absolute/path/to/playlists" uv --directory ../rekordbx-mcp run --locked \
  --with fastapi --with uvicorn --with mutagen \
  uvicorn --app-dir ../neon-crate --reload-dir ../neon-crate --reload-dir src \
  server:app --port 8000 --reload
```

Then set the app's API URL to `http://localhost:8000` and enable API mode.
The server provides `GET /api/playlists`, `GET /api/playlists/{playlist_id}`,
`GET /api/stream?playlist_id=...&track_id=...`, `GET /api/collection/status`,
`GET /api/collection/stream/{track_id}`, `POST /api/collection/lookup`, and
`POST /api/playlists/{playlist_id}/tracks/swap`.
Export JSON contains an ordered `tracks`
array with each Rekordbox track ID and its absolute file path together. The API
validates those entries against the M3U8; older ID-only plans still pair with
M3U8 entries by order.
The active deck displays embedded audio cover art, with a music-note placeholder
when no supported artwork is available.
Rows with an ID use an exact collection lookup; playlists without a matching
plan fall back to artist/title lookup. Playlist streaming is restricted to
files referenced by playlists in the configured folder; collection streaming
resolves only active snapshot track IDs. Track removal uses
`DELETE /api/playlists/{playlist_id}/tracks` with a JSON `track_ids` list and
updates both playlist and plan files; it only works with the repository's
`playlists/` folder. Swapping a track also requires confirmation and updates its
M3U8 entry and matching JSON plan when one exists.

Each track row has a Lookup action that expands inline results: it returns the
exact Rekordbox record when a plan ID is available, including its rating and
play count, or searches by artist and title for standalone playlists. A result's
Play loads the collection track into the main deck. Swap replaces the source
track in the selected playlist after confirmation. The local API uses collection
file locations internally for playback and playlist updates without sending
paths to the browser.
The MCP worker starts on the first lookup, so
CrateDeck can browse and play playlists without it. Close Rekordbox and its
background agents before the first lookup; the worker creates a fresh verified
snapshot, stays connected while the API runs, and stops with the API. The header
shows whether the MCP worker is idle, connecting, connected, or in an error
state. A lookup startup failure does not interrupt playlist browsing or playback.
