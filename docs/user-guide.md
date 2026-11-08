# CrateBox user guide

[Product overview](../README.md) · [CrateBox app](../cratebox/README.md) · [Adapter details](../cratebox/rekordbx-mcp/README.md)

**CrateBox — A direct, playful nod to Rekordbox, hinting at crate management and track prep.**

CrateBox combines a local playlist UI, REST API, Core services, and MCP endpoint. A small Rekordbox adapter provides generic data from a verified snapshot. The app runs on macOS with Python 3.12, uv, Node.js, and Codex. Docker is not used.

The Rekordbox database, playlists, XML exports, analysis files, and metadata are read-only. CrateBox can update only embedded cover artwork on an MP3/M4A selected from a local crate or a Rekordbox playlist. It stages and verifies the change before atomically replacing the selected audio file; it does not retain a backup. Other audio edits are not allowed.

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

When the Rekordbox worker first connects:

- If Rekordbox and its agents are closed, it creates and verifies a fresh copy of `master.db`.
- If Rekordbox is running, it reuses only the newest verified snapshot already on disk. It never copies the live database and fails if no valid snapshot is available.

Snapshots remain under the existing repository-root `rekordbx-mcp/.cache/rekordbox-snapshots/` location. The worker pins one verified snapshot for its lifetime. To refresh it, close Rekordbox and its agents, then restart the worker or API. A collection-startup failure does not interrupt local playlist browsing or playback.

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

CrateBox Core resolves active snapshot records, checks the audio files, and writes the M3U8 to `playlists/` with its CrateBox JSON metadata in `.cratebox/crates/`. The JSON records order, duplicates, IDs, paths, and collection metadata. Existing JSON files in `output/` are left untouched and are not read. The audio paths are kept out of the tool response and browser payloads. Passing `file_paths` sends those paths as tool inputs; prefer IDs when possible.

If the requested name already exists, confirm whether to replace the existing pair or use a different name. CrateBox never imports a playlist into Rekordbox. Import the M3U8 yourself when ready.

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
| Collection worker says to close Rekordbox | Quit Rekordbox and its background agents. If Rekordbox must remain open, an existing verified snapshot is required. |
| Snapshot hash invalid | Do not edit the snapshot or manifest. Close Rekordbox and restart the worker to create a new verified copy. |
| Collection results look old | Close Rekordbox, then restart the API/worker to refresh its pinned snapshot. |
| MCP tools do not appear | Check that the repository is trusted, confirm the configured paths, then restart the CrateBox MCP connection. |
| Playlists changed outside CrateBox | Keep the UI visible or focus it; it checks for edits every two seconds and refreshes the active playlist without replacing the loaded Deck. |

## 8. Tests and code locations

Adapter tests:

```sh
uv --directory cratebox/rekordbx-mcp run --locked pytest -q
```

CrateBox API/Core tests:

```sh
uv --directory cratebox/rekordbx-mcp run --locked --with ddgs --with fastapi --with mutagen pytest ../tests -q
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

The adapter uses a verified snapshot, read-only SQLCipher connection, SQL authorizer, and fixed upstream reading allowlist. It runs with normal user permissions; it is not OS filesystem or network isolation. Returned collection metadata becomes part of the Codex conversation, so the conversation is not fully offline.

The adapter never edits Rekordbox's original database, playlists, XML, analysis files, or metadata. CrateBox artwork editing is limited to its documented backup-verified MP3 operation. M3U8 exports contain local audio paths; keep them private.
