# CrateBox app

CrateBox is a local playlist and playback app. The UI talks only to the FastAPI API. The API uses the importable `core/` services for collection matching, playlist revisions, shared mutation locks, Spotify, Sockseek, and playlist export. REST and Streamable HTTP MCP are mounted in one process at port 8000; the MCP path is `/mcp/`.

## Start the app

From this directory:

```sh
npm run dev:all
```

The UI runs at <http://localhost:4444/> and the API at <http://localhost:8000/>. The API serves the MCP at <http://localhost:8000/mcp/>. Codex uses the repository launcher in `scripts/cratebox-mcp-launcher.py`; it checks these local endpoints and starts only missing services before proxying the HTTP MCP over stdio.

For a production-style local run, build once and start the API/MCP with the built UI:

```sh
npm run build
npm run start:all
```

This serves the compiled UI without Vite's development server. Use `npm run dev:all` while editing the app.

The protected Rekordbox MCP worker starts lazily when collection data is requested. If it cannot start, local playlist browsing and playback remain available.

## Architecture and paths

See [architecture.md](architecture.md) for the definition of a CrateBox crate and the boundaries between the UI, API, Core, MCP, and Rekordbox adapter.

- `src/` contains the UI.
- `api/` defines REST and MCP adapters and keeps local audio paths on the server.
- `core/` contains shared app behavior used by REST and MCP.
- `tests/` contains Core and API tests.
- `server.py` preserves the `server:app` Uvicorn entry point.
- `rekordbx-mcp/` contains the generic snapshot-backed Rekordbox provider and its own tests.

The Core exporter writes M3U8 playlists to the repository's `playlists/` folder and CrateBox JSON metadata to `.cratebox/crates/`. Existing JSON files in `output/` are left untouched and are not read. Replacement requires explicit confirmation. No export imports into Rekordbox.

CrateBox may embed artwork only into an MP3 selected from the repository's own `playlists/` folder after making and verifying an exact backup in `output/audio-backups/`. Original Rekordbox data remains read-only.

## Tests

From the repository root:

```sh
uv --directory cratebox/rekordbx-mcp run --locked --with ddgs --with fastapi --with mutagen pytest ../tests -q
```

From this directory, run frontend checks:

```sh
npm test
npm run build
```
