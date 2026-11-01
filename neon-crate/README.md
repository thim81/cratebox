# CrateDeck local playlist API

The app reads `.m3u` and `.m3u8` playlists through a small local FastAPI server.
In the repository's `playlists/` folder, tracks can be removed or replaced in a playlist;
the audio file is never deleted. Other configured playlist folders remain read-only.
The API implementation is organized by feature in `api/`; `server.py` preserves the
`server:app` entry point used by the existing launcher.

From this folder, run:

```sh
uv --directory ../rekordbx-mcp run --locked --with fastapi --with uvicorn --with mutagen --with ddgs \
  uvicorn --app-dir ../neon-crate --reload-dir ../neon-crate --reload-dir src \
  server:app --port 8000 --reload
```

By default, playlists are read from the repository root `playlists/` folder. To use another folder:

```sh
PLAYLIST_DIR="/absolute/path/to/playlists" uv --directory ../rekordbx-mcp run --locked \
  --with fastapi --with uvicorn --with mutagen --with ddgs \
  uvicorn --app-dir ../neon-crate --reload-dir ../neon-crate --reload-dir src \
  server:app --port 8000 --reload
```

Then set the app's API URL to `http://localhost:8000`.
The server provides `GET /api/playlists`, `GET /api/playlists/{playlist_id}`,
`GET /api/stream?playlist_id=...&track_id=...`, `GET /api/collection/status`,
`GET /api/collection/stream/{track_id}`, `POST /api/reveal`,
`POST /api/collection/lookup`,
`GET /api/rekordbox/playlists`, `GET /api/rekordbox/playlists/{playlist_id}/tracks`,
`POST /api/rekordbox/playlists/{playlist_id}/copy`, `POST /api/images/search`,
`PUT /api/artwork`, `PUT /api/artwork/embed`, and
`POST /api/playlists/{playlist_id}/tracks/swap`.
Export JSON contains an ordered `tracks`
array with each Rekordbox track ID and its absolute file path together. The API
validates those entries against the M3U8; older ID-only plans still pair with
M3U8 entries by order.
The active deck displays embedded audio cover art, with a music-note placeholder
when no supported artwork is available. Its Finder button reveals the active
audio file in Finder on macOS.
Use Search Image beside a crate name or active track to search music catalogues
first. iTunes helps identify track and album metadata; MusicBrainz/Cover Art
Archive supplies matching cover images. CrateDeck supplements a short catalogue
result set with distinct DuckDuckGo images, keeping curated covers first and
filling up to 24 results when available. Each result is labeled with its source;
catalogue results remain visible if DuckDuckGo is unavailable. Crate artwork
stores the selected image URL in `output/cratedeck-artwork.json`. Track artwork
is downloaded only when the user
chooses **Embed into MP3**; CrateDeck accepts public HTTPS JPEG/PNG files up to
8 MiB, makes a byte-for-byte backup in `output/audio-backups/`, stages and checks
the ID3 update, then atomically replaces the selected MP3. This operation works
only for tracks in the repository's own `playlists/` folder, rejects symlinked
or hard-linked targets, and supports ID3v2.3/v2.4 tags. To undo a change, stop
CrateDeck and restore that track's matching backup file. Search providers may
rate-limit requests and image hosts may block previews or downloads; a failed
track image falls back to existing embedded artwork.
Rows with an ID use an exact collection lookup; playlists without a matching
plan fall back to artist/title lookup. Playlist streaming is restricted to
files referenced by playlists in the configured folder; collection streaming
resolves only active snapshot track IDs. Track removal uses
`DELETE /api/playlists/{playlist_id}/tracks` with a JSON `track_ids` list and
updates both playlist and plan files; it only works with the repository's
`playlists/` folder. Swapping a track also requires confirmation and updates its
M3U8 entry and matching JSON plan when one exists.
The sidebar's Rekordbox tab browses snapshot playlists as read-only. Copying a
playlist uses the exporter to create an editable CrateDeck M3U8/JSON pair;
updating an existing local copy requires confirmation. Rekordbox items start at
level 0, follow Rekordbox's sibling sequence, and folders open to their children.

Each track row has a Lookup action that expands inline results: it returns the
exact Rekordbox record when a plan ID is available, including its rating and
play count, or searches by artist and title for standalone playlists. A result's
Play loads the collection track into the main deck. Swap replaces the source
track in the selected playlist after confirmation. The local API uses collection
file locations internally for playback and playlist updates without sending
paths to the browser.
The MCP worker starts on the first lookup or Rekordbox playlist browse, so
CrateDeck can browse local playlists without it. Close Rekordbox and its
background agents before the first collection action; the worker creates a fresh verified
snapshot, stays connected while the API runs, and stops with the API. The header
shows whether the MCP worker is idle, connecting, connected, or in an error
state. A lookup startup failure does not interrupt playlist browsing or playback.

## CrateDeck tests

CrateDeck API tests live in `neon-crate/tests/`. Run them from the repository
root with the MCP project's locked Python environment:

```sh
uv --directory rekordbx-mcp run --locked --with ddgs --with fastapi --with mutagen \
  pytest ../neon-crate/tests -q
```
