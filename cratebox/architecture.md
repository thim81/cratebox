# CrateBox architecture

## Core concepts

A **crate** is a CrateBox-owned, ordered working set of tracks for preparing and playing a DJ set. A crate can include track order, repeated tracks, and CrateBox metadata. When exported, it has two related files: an M3U8 playlist in the repository's `playlists/` directory for playback or Rekordbox import, and a JSON crate record in `.cratebox/crates/` for CrateBox metadata. The JSON record is private app state; the M3U8 is the portable playlist file.

Some API routes, tools, and implementation names still say “playlist” because they describe the M3U format or preserve existing interfaces. In the product model, the app-owned working set and its metadata are the crate.

CrateBox uses “crate” for this app-owned concept. A Rekordbox playlist is source collection data that CrateBox can browse or copy; it is not itself a CrateBox crate until copied or prepared in CrateBox. CrateBox does not write crates into Rekordbox.

## Components

- **UI (`src/`)** presents crates and collection results, handles editing and playback, and calls only the REST API.
- **REST API (`api/`)** adapts HTTP requests to Core, serves browser-safe responses, and keeps local audio paths on the server.
- **Core (`core/`)** owns crate and playlist behavior shared by REST and MCP: parsing, validation, mutation, matching, export, and related integrations.
- **CrateBox MCP (`api/`)** exposes an allowlisted local MCP interface in the same process as REST and delegates behavior to Core.
- **Rekordbox adapter (`rekordbx-mcp/`)** supplies generic collection data from verified read-only snapshots. It does not own CrateBox crate behavior.

## Storage boundaries

- `.cratebox/crates/` stores CrateBox-owned JSON crate records; `.cratebox/` is local app state.
- `playlists/` stores M3U/M3U8 files used for local playback and optional manual import into Rekordbox.
- Existing JSON files in `output/` are not read or migrated.
- The original Rekordbox database and related collection files remain untouched.

REST and MCP share the same Core instances and mutation locks, so edits through either interface use the same application rules.
