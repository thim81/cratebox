# CrateBox user guide

## Rekordbox playlist editing

CrateBox reads the original Rekordbox database directly while Rekordbox and its agents are closed. Local CrateBox playlists stay independent. Ordinary Rekordbox playlists support immediate creation, rename, add, remove, replacement, and drag reordering; no separate Save action is needed. Playlist IDs and unaffected entry identities are preserved.

The first edit in each session creates a verified recovery point; further edits reuse it for up to five minutes. Backups live in `.cratebox/rekordbox-backups/`, outside the Rekordbox directory, and include `masterPlaylists6.xml` when present. Required backup failures block writes. Process checks, short transactions, revision checks, and result validation protect each edit; they do not guarantee that another application cannot start between checks. See the [repository instructions](../AGENTS.md).

[Product overview](../README.md) · [CrateBox app](../cratebox/README.md) · [Adapter details](../cratebox/rekordbx-mcp/README.md)

**CrateBox — A direct, playful nod to Rekordbox, hinting at crate management and track prep.**

CrateBox combines a local playlist UI, REST API, Core services, and MCP endpoint. A small Rekordbox adapter provides generic data directly from the original database. The app runs on macOS with Python 3.12, uv, Node.js, and Codex. Docker is not used.

Direct database changes are limited to the playlist operations above. CrateBox can separately update embedded artwork or a loaded-track rating on an MP3/M4A selected from a local crate or verified Rekordbox playlist membership. It stages and verifies the change before atomically replacing the selected audio file; it does not retain a backup. Other audio edits remain outside these permissions.

## 1. Install

From the repository root:

```sh
uv --directory cratebox/rekordbx-mcp sync --locked --python 3.12
cd cratebox
npm install
```

The Python project uses Python 3.12. uv keeps that environment in `cratebox/rekordbx-mcp/.venv/`.

## 2. Configure Codex

Open this repository as a trusted local project in Codex. The repository contains `.codex/config.toml`, which starts `scripts/cratebox-mcp-launcher.py`. It checks the local CrateBox API/MCP on port 8000 and UI on port 4444, starts only missing services, waits for both to become ready, and proxies the API's Streamable HTTP MCP to Codex over stdio.

The HTTP MCP is mounted in the same process as REST at `http://127.0.0.1:8000/mcp/`. The launcher does not create a separate MCP daemon. The API starts the protected Rekordbox worker only when a collection operation is first requested.

For another Codex client, use [`cratebox-mcp.example.toml`](../cratebox-mcp.example.toml) as a template and update its absolute paths. The example does not change another active MCP configuration.

## 3. Start a session safely

Restart Codex or its CrateBox MCP connection. If services are missing, the launcher starts them; if they're already healthy, it reuses them. The UI is at <http://localhost:4444/> and the API is at <http://localhost:8000/>.

The collection worker opens the original database directly. Close Rekordbox and its background agents before browsing or editing. If process checks fail or a transaction journal is present, access is rejected. Close Rekordbox cleanly and try the request again. Local playlist browsing and playback remain independent.

In the Rekordbox tab, select an ordinary playlist to edit it. Drop tracks to reorder; use Add track, Replace track, or the row removal button; use the pencil beside the active playlist to rename it. Create playlist creates an empty Rekordbox playlist at the root. Smart playlists and folders remain browse-only. Names commit when confirmed, and each other editing action persists once. Errors are displayed without automatically retrying the write. Click Refresh after a conflicting or failed edit.

For another collection location, set `REKORDBOX_DATABASE` to its absolute `master.db` path before launching the API. Set `REKORDBOX_BACKUP_DIRECTORY` to override the backup folder; it must be outside the original database directory.

### Backup and recovery

The first edit creates and verifies a backup. Edits within the next 300 seconds reuse that recovery point; a subsequent edit after expiry creates another. No backups run while idle and none are automatically pruned. Restoring a recovery point can undo successful edits made since it was taken.

List backups and explicitly restore one with Rekordbox and its agents closed:

```sh
uv --directory cratebox/rekordbx-mcp run --locked rekordbx-mcp backup-list
uv --directory cratebox/rekordbx-mcp run --locked rekordbx-mcp restore --backup-id BACKUP_ID
```

Both commands accept `--source /absolute/path/master.db` and `--backup-directory /absolute/path/backups`. Use the same source and backup directory configured for the API. Restore verifies the selected recovery point and preserves current files first, even if damaged or missing. An interrupted or uncertain commit blocks further edits until inspected and explicitly restored. Database and companion XML replacement are separate file operations; interrupted recovery remains blocked and can be retried explicitly.

For foreground diagnostics, run from `cratebox/`:

```sh
npm run dev:all
```

This starts the Vite UI and API/MCP together. Logs from the Codex launcher are written to `/tmp/cratebox-api.log` and `/tmp/cratebox-ui.log`.

For a production-style local run, build and start from `cratebox/`:

```sh
npm run build
npm run start:all
```

This serves the built UI without Vite's development server while keeping REST and MCP on the API process. Stop either foreground command with Ctrl+C.

## 4. Explore and prepare playlists

Try:

> Search my collection for house tracks between 120 and 128 BPM. Propose an approximately 60-minute playlist using only returned track IDs. Show artist, title, BPM, key, and duration, explain your choices, and flag uncertainty about energy or mood.

Other examples:

> Find 30 tracks suitable for a 90s dance set. Search the collection first and flag releases whose era is unclear.

> Browse my Rekordbox playlists and copy the selected playlist into CrateBox as "Friday warm-up".

The conversational MCP exposes playlist operations, collection search and lookup, Rekordbox playlist browsing, `export_playlist`, `spotify_tracklist`, and `create_sockseek_list`. Internal collection resolution, pagination, and path-returning operations are excluded from its explicit allowlist.

## 5. Export and import playlists

Ask Codex to export an ordered ID list:

> Export the final selection with `export_playlist`, named "House warm-up", preserving the agreed order. Provide links to the M3U8 and JSON files.

CrateBox Core resolves active collection records, checks the audio files, and writes the M3U8 to `playlists/` with its CrateBox JSON metadata in `.cratebox/crates/`. The JSON records order, duplicates, IDs, paths, and collection metadata. Existing JSON files in `output/` are left untouched and are not read. The audio paths are kept out of the tool response and browser payloads. Passing `file_paths` sends those paths as tool inputs; prefer IDs when possible.

If the requested name already exists, confirm whether to replace the existing pair or use a different name. CrateBox does not currently import a playlist into Rekordbox. Import the M3U8 yourself when ready.

## 6. Update the upstream adapter

Upstream updates are explicit. Check for a new revision:

```sh
uv --directory cratebox/rekordbx-mcp run --locked rekordbx-mcp update-upstream --check
```

Stop active MCP sessions, then install and run compatibility/safety checks:

```sh
uv --directory cratebox/rekordbx-mcp run --locked rekordbx-mcp update-upstream
```

The updater pins an exact commit and rolls back dependency files if checks fail. Review and commit the changed `cratebox/rekordbx-mcp/pyproject.toml` and `cratebox/rekordbx-mcp/uv.lock` after a successful update. New upstream tools are not exposed automatically.

## 7. Troubleshooting

| Symptom | What to do |
| --- | --- |
| CrateBox MCP startup fails | Check `/tmp/cratebox-api.log` and `/tmp/cratebox-ui.log`; confirm ports 8000 and 4444 are available. Run `npm run dev:all` from `cratebox/` to diagnose in the foreground. |
| Collection worker says to close Rekordbox | Quit Rekordbox and its background agents, then retry the request. Collection browsing also requires them closed. |
| Backup verification failed | The edit is blocked. Inspect the backup storage and use the recovery commands above if required. |
| Collection results look old | Close Rekordbox, then refresh the playlist view; reads use the original database. |
| MCP tools do not appear | Check that the repository is trusted, confirm the configured paths, then restart the CrateBox MCP connection. |
| Playlists changed outside CrateBox | Keep the UI visible or focus it; it checks for edits every two seconds and refreshes the active playlist without replacing the loaded Deck. |

## 8. Tests and code locations

Adapter tests:

```sh
uv --directory cratebox/rekordbx-mcp run --locked pytest -q
```

CrateBox API/Core tests:

```sh
uv --directory cratebox/rekordbx-mcp run --locked --with ddgs --with fastapi --with mutagen --with playwright pytest ../tests -q
```

Frontend tests and build, from `cratebox/`:

```sh
npm test
npm run build
```

| Location | Purpose |
| --- | --- |
| `cratebox/src/` | UI |
| `cratebox/api/` | REST and MCP adapters |
| `cratebox/core/` | Shared playlist, export, lookup, Spotify, Sockseek, lock, and revision services |
| `cratebox/tests/` | CrateBox API and Core tests |
| `cratebox/rekordbx-mcp/src/rekordbx_mcp/` | Generic protected collection adapter |
| `cratebox/rekordbx-mcp/tests/` | Adapter tests |

## Privacy and limits

The adapter uses direct SQLCipher access, process checks, serialized operations, and a fixed tool allowlist. It runs with normal user permissions, not OS filesystem or network isolation. Returned collection metadata can become part of the Codex conversation. Browser payloads and conversational tools omit audio paths.

Permitted playlist edits modify the original database and required playlist companion files. They do not authorize collection metadata or analysis edits. Embedded artwork and loaded-track file-rating updates retain their separate permissions. M3U8 exports and database backups contain private local-library data; keep them private.
