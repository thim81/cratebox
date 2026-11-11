# CrateBox architecture

## Rekordbox playlist editing

CrateBox reads the original Rekordbox database directly while Rekordbox and its agents are closed. Local CrateBox playlists stay independent. Ordinary Rekordbox playlists support immediate creation, rename, add, remove, replacement, and drag reordering; no separate Save action is needed. Playlist IDs and unaffected entry identities are preserved.

The first edit in each session creates a verified recovery point; further edits reuse it for up to five minutes. Backups live in `.cratebox/rekordbox-backups/`, outside the Rekordbox directory, and include `masterPlaylists6.xml` when present. Required backup failures block writes. Process checks, short transactions, revision checks, and result validation protect each edit; they do not guarantee that another application cannot start between checks. See the [repository instructions](../AGENTS.md).

## Core concepts

A **crate** is a CrateBox-owned, ordered working set of tracks for preparing and playing a DJ set. A crate can include track order, repeated tracks, and CrateBox metadata. When exported, it has two related files: an M3U8 playlist in the repository's `playlists/` directory for playback or Rekordbox import, and a JSON crate record in `.cratebox/crates/` for CrateBox metadata. The JSON record is private app state; the M3U8 is the portable playlist file.

Some API routes, tools, and implementation names still say “playlist” because they describe the M3U format or preserve existing interfaces. In the product model, the app-owned working set and its metadata are the crate.

CrateBox uses “crate” for this app-owned concept. A Rekordbox playlist is source collection data that CrateBox can browse or copy; it is not itself a CrateBox crate until copied or prepared in CrateBox. CrateBox does not currently write crates into Rekordbox.

## Components

- **UI (`src/`)** presents crates and collection results, handles editing and playback, and calls only the REST API.
- **REST API (`api/`)** adapts HTTP requests to Core, serves browser-safe responses, and keeps local audio paths on the server.
- **Core (`core/`)** owns crate and playlist behavior shared by REST and MCP: parsing, validation, mutation, matching, export, and related integrations.
- **CrateBox MCP (`api/`)** exposes an allowlisted local MCP interface in the same process as REST and delegates behavior to Core.
- **Rekordbox adapter (`rekordbx-mcp/`)** supplies generic collection reads and controlled playlist edits directly against the original database. It does not own CrateBox crate behavior.

CrateBox can update embedded cover art and loaded-track ratings for a permitted audio file selected through a local crate or resolved by its track ID in the Rekordbox collection. The API stages and verifies the changed tags, then atomically replaces the audio file; it keeps no backup. These audio-tag operations are separate from direct playlist database edits; collection metadata, cues, beatgrids, XML exports and analysis files are not edited.

## Storage boundaries

- `.cratebox/crates/` stores CrateBox-owned JSON crate records; `.cratebox/` is local app state.
- `playlists/` stores M3U/M3U8 files used for local playback and optional manual import into Rekordbox.
- Existing JSON files in `output/` are not read or migrated.
- The original Rekordbox database and required playlist companion files are updated only by permitted playlist edits, following the backup and transaction policy above.

REST and MCP share the same Core instances and mutation locks, so edits through either interface use the same application rules.
