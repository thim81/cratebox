# CrateBox

## Rekordbox playlist editing

CrateBox reads the original Rekordbox database directly while Rekordbox and its agents are closed. Local CrateBox playlists stay independent. Ordinary Rekordbox playlists support immediate creation, rename, add, remove, replacement, and drag reordering; no separate Save action is needed. Playlist IDs and unaffected entry identities are preserved.

The first edit in each session creates a verified recovery point; further edits reuse it for up to five minutes. Backups live in `.cratebox/rekordbox-backups/`, outside the Rekordbox directory, and include `masterPlaylists6.xml` when present. Required backup failures block writes. Process checks, short transactions, revision checks, and result validation protect each edit; they do not guarantee that another application cannot start between checks. See the [repository instructions](AGENTS.md).

<img src="./cratebox/public/logo/cratebox-logo.png" width="200"/>

**CrateBox — Crate management and track prep for Rekordbox.**

CrateBox is a local playlist workspace for preparing and playing DJ sets. Its UI, REST API, and MCP interface share one Core in the `cratebox/` app. A small protected Rekordbox adapter supplies generic collection data and permitted playlist mutations.

In CrateBox's domain model, a **crate** is an app-owned ordered working set. Its JSON record lives in `.cratebox/crates/`; its exported M3U8 lives in `playlists/`. See the [architecture overview](cratebox/architecture.md) for the component and storage boundaries.

The app runs on macOS with Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js, and Codex. Rekordbox playlist changes are limited to the editing operations described above.

## Features

- Browse, edit, and play local M3U/M3U8 playlists.
- Search and play collection tracks while Rekordbox is closed.
- Import Rekordbox selections into editable CrateBox playlists.
- Look up Spotify tracklists and create Sockseek search lists.
- Export ordered track IDs as an M3U8 playlist and matching JSON plan.
- Keep collection audio paths inside local services; responses to the browser and conversational MCP do not include audio paths.
- Refresh playlists changed by another local app without interrupting the loaded Deck.

## Install

From the repository root:

```sh
uv --directory cratebox/rekordbx-mcp sync --locked --python 3.12
cd cratebox
npm install
```

Open this repository as a trusted local project in Codex. The project MCP config at `.codex/config.toml` launches `scripts/cratebox-mcp-launcher.py`. The launcher checks the local API/MCP at `127.0.0.1:8000` and UI at `127.0.0.1:4444`, starts only missing services, verifies readiness, then proxies the API's `/mcp/` endpoint to Codex over stdio. MCP is hosted in the same process as REST; the protected Rekordbox worker starts lazily when a collection feature is first used.

For another local Codex client, use [cratebox-mcp.example.toml](cratebox-mcp.example.toml) as a configuration example and adjust the absolute paths for your machine. It does not modify the active Codex configuration.

## Run manually

Start the UI and API together from `cratebox/`:

```sh
npm run dev:all
```

The UI is at <http://localhost:4444/>. REST and Streamable HTTP MCP are served by the same API at <http://localhost:8000> and <http://localhost:8000/mcp/>. The API keeps local file locations on the server.

For a production-style local run, build first, then start the API/MCP and built UI without Vite's development server:

```sh
npm run build
npm run start:all
```

Both modes use ports 8000 and 4444. Stop the foreground command with Ctrl+C.

The launcher writes service logs to `/tmp/cratebox-api.log` and `/tmp/cratebox-ui.log`. If startup fails, inspect those logs. The manual `dev:all` command is useful for foreground diagnostics.

## Use MCP

The local CrateBox MCP exposes playlist operations, collection search and lookup, Rekordbox playlist browsing, `export_playlist`, `spotify_tracklist`, and `create_sockseek_list`. Tool discovery and direct calls use an explicit allowlist. Internal collection resolution and pagination are unavailable to conversational clients.

For export, pass ordered `track_ids` or `file_paths`. IDs preserve duplicates and order. File locations must be absolute and resolve to exactly one active track. The exporter checks file existence and writes M3U8 files only to `playlists/` and CrateBox JSON metadata to `.cratebox/crates/`. Existing JSON files in `output/` are left untouched and are not read. Existing pairs require explicit confirmation before replacement. File export stays separate from direct Rekordbox playlist editing; the exporter does not import files into the collection.

## Data protection

The Rekordbox adapter uses an explicit original database path, SQLCipher, process checks, and a fixed tool allowlist. Collection operations are unavailable while Rekordbox or its agents are running; local CrateBox playlists remain usable. Each request closes its database connection afterward. There is no snapshot fallback.

Only playlist names, membership, order, creation, and required playlist companion updates may be changed. Track metadata, cues, beatgrids, XML exports, and analysis files remain outside database-editing scope. Embedded artwork and loaded-track file-rating edits retain their separate, existing permissions.

Read the [user guide](docs/user-guide.md), [CrateBox API notes](cratebox/README.md), and [adapter protection details](cratebox/rekordbx-mcp/README.md).

## Development and tests

Frontend checks from `cratebox/`:

```sh
npm test
npm run build
```

Python tests from the repository root:

```sh
uv --directory cratebox/rekordbx-mcp run --locked pytest -q
uv --directory cratebox/rekordbx-mcp run --locked --with ddgs --with fastapi --with mutagen --with playwright pytest ../tests -q
```

The Rekordbox MCP is pinned and unmodified upstream. Update it explicitly with `rekordbx-mcp update-upstream`; see the [adapter update guide](docs/user-guide.md#6-update-the-upstream-mcp).
