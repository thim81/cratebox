# Rekordbx user guide

[Product overview](../README.md) · [Adapter documentation](../rekordbx-mcp/README.md)

Use Codex to explore your existing Rekordbox collection and propose playlists
using music you already own. The project connects Codex to a protected version
of [rekordbox-mcp](https://github.com/davehenke/rekordbox-mcp).

**The original Rekordbox data must never be changed by this application.**
The adapter works against a separate, verified, read-only copy of `master.db`.
It does not edit existing playlists, analysis files, audio files or their tags.
It runs natively on macOS with uv; Docker is not used.

## What you can use today

- Search your collection by artist, title, genre, BPM and key.
- Explore existing playlists, ratings, play counts and DJ history.
- Ask Codex to select and order tracks, explaining its choices.
- Validate proposed track IDs against the copied collection.
- Export ordered selections as M3U8, with a JSON record of the track IDs.
- Refresh the collection copy automatically whenever the MCP starts.
- Update the upstream MCP with compatibility tests and rollback.

Playlist proposals are made and refined in the Codex conversation. Ask the
`export_playlist` tool to save the final selection outside Rekordbox.
Duplicate-free import into Rekordbox remains unverified.

## 1. Install the dependencies

You need macOS, Git, uv, Python 3.12, and Codex
with access to this local project. Network access is needed for installation
and updates.

These commands assume the repository is at `/Users/thim/Sites/rekordbx`.
Change that path if you move it. All commands below run from the repository
root unless stated otherwise.

```sh
cd /Users/thim/Sites/rekordbx
uv --directory rekordbx-mcp sync --locked --python 3.12
uv --directory rekordbx-mcp run --locked rekordbx-mcp --help
```

The Python project requires Python 3.12, even if your default `python3` is
newer. uv creates its environment under `rekordbx-mcp/.venv/`.

The adapter does not require a separate OpenAI API key. Codex handles the AI
conversation; this local MCP supplies collection metadata.

## 2. Configure Codex

Open this repository as a local project in Codex. Add the following configuration
to `/Users/thim/Sites/rekordbx/.codex/config.toml`, creating that file if needed.
If the file already exists, merge this server table into it and preserve its
other settings. Keep only one `mcp_servers.rekordbox` table.

```toml
[mcp_servers.rekordbox]
command = "/opt/homebrew/bin/uv"
args = [
  "--directory", "/Users/thim/Sites/rekordbx/rekordbx-mcp",
  "run", "--locked", "--offline",
  "rekordbx-mcp", "start"
]
startup_timeout_sec = 120
tool_timeout_sec = 120
enabled_tools = [
  "search_tracks",
  "get_track_details",
  "get_playlists",
  "get_playlist_tracks",
  "get_library_stats",
  "get_tracks_by_bpm_range",
  "get_tracks_by_key",
  "get_most_played_tracks",
  "get_top_rated_tracks",
  "get_unplayed_tracks",
  "search_tracks_by_filename",
  "analyze_library",
  "validate_track_ids",
  "get_history_sessions",
  "get_session_tracks",
  "get_recent_sessions",
  "get_history_stats",
  "search_history_sessions",
  "export_playlist"
]
```

This is also available in
[`codex-mcp.example.toml`](../rekordbx-mcp/codex-mcp.example.toml). The template
is not automatically installed. Use `command -v uv` to check the executable
path on another machine.

If you already installed the previous configuration, add `"export_playlist"`
to its `enabled_tools` array. Restart the MCP with Rekordbox closed to load the
new tool. Preserve the other settings in your configuration.

Project-scoped MCP configuration requires a trusted project. Codex also supports
user-level configuration in `~/.codex/config.toml`; use one scope for this
server to avoid duplicate connections. After saving, restart the MCP connection
or reopen Codex. See the official
[MCP configuration guide](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

The tool allowlist limits what Codex can call. Actual read-only access is
enforced by the snapshot's read-only database connection and SQL authorizer.
Always launch `rekordbx-mcp start` rather than the upstream
`rekordbox-mcp` command.

## 3. Start a session safely

Codex automatically launches the configured `rekordbx-mcp start` command when
it initializes the MCP connection. No separate Terminal server is required.

1. Open or restart the configured Rekordbox MCP connection in Codex.
2. Wait for the connection to be ready.
3. Ask Codex: **“Use the Rekordbox MCP to show my library statistics.”**

When Rekordbox is closed, `start`:

1. Refuses to copy a database with WAL, SHM or journal sidecars present.
2. Creates a new independent copy of the current `master.db`.
3. Rechecks processes, source metadata and hashes after copying.
4. Marks the copy read-only and starts the MCP against that verified snapshot.

When Rekordbox is running, `start` skips copying and serves the newest verified
snapshot already on disk. If no snapshot exists, startup fails and asks you to
close Rekordbox and create one. It never closes Rekordbox or deletes source sidecars.

The default source is:

```text
/Users/thim/Library/Pioneer/rekordbox/master.db
```

Fresh copies are stored under:

```text
rekordbx-mcp/.cache/rekordbox-snapshots/<snapshot-id>/
  master.db
  manifest.json
```

A running MCP keeps using its fixed snapshot. If you add or change tracks in
Rekordbox, close Rekordbox and restart the MCP to obtain a new copy. You can
reopen Rekordbox once copying finishes. Copies are retained locally; they are
ignored by Git and consume disk space.

For terminal troubleshooting only, you can start the same launcher yourself:

```sh
uv --directory rekordbx-mcp run --locked rekordbx-mcp start
```

This starts an MCP stdio server and waits for a client, so it does not show an
interactive playlist prompt. Startup diagnostics go to stderr. Press Ctrl+C to
stop a manually started process. Codex normally launches its own instance using
the configuration above.

For a nonstandard library location, add `--source` followed by the absolute
path to `master.db` after `"start"` in the MCP arguments.

## 4. Ask for playlists

Start with a prompt that asks Codex to retrieve tracks before selecting them:

> Use the Rekordbox MCP to search my collection for house tracks between
> 120 and 128 BPM. Propose an approximately 60-minute playlist. Use only
> returned track IDs and validate the final IDs. Show artist, title, BPM,
> key, duration, a selection reason, and estimated total duration.

Other requests to try:

> Build a 90-minute après-ski proposal with Belgian classics, singalongs
> and an energetic finale. Search my collection first. Explain any gaps
> and flag uncertainty about energy or mood.

> Find 30 tracks from my collection suitable for a 90s dance set. Check
> available details before claiming a release year; flag tracks whose era
> cannot be verified.

> Show my existing party playlists, then propose a new order for a
> 20-track warm-up set using tracks from them. Do not change those playlists.

You can refine a proposal in the same chat:

> Remove tracks 4 and 8, replace them with other validated candidates,
> and make the final 15 minutes more energetic.

Track duration totals are estimates for full tracks, not a prediction of
mixed-set length. Energy, mood, popularity and singalong suitability are not
measured audio features here; ask Codex to distinguish musical judgment from
stored metadata. The upstream tool models do not expose every database field.

The copied catalog can contain references to missing audio files. Reading tools
do not check your audio folders, so a valid track ID does not guarantee that
the file is currently available. The exporter checks selected files and reports
missing ones before writing a playlist.

## 5. Export and import playlists

Once you have agreed on a selection in chat, ask:

> Use `export_playlist` to export the final track IDs in the agreed order.
> Name it "House warm-up" and give me links to both generated files.

The tool accepts `name` and exactly one ordered array: `track_ids` or `file_paths`.
It uses the running session's verified snapshot; it does not read the live
database. With IDs, audio paths are resolved locally. With file locations, each
path must match exactly one active track in that snapshot, and is resolved to
its track ID. Files outside the collection, deleted-only matches, and ambiguous
matches are refused. Paths must be absolute local filenames, not `file://` URLs,
relative paths or folders, and must match the stored path exactly.

For example, these are alternative tool arguments:

```json
{"name": "House warm-up", "track_ids": ["123", "456", "789"]}
```

```json
{"name": "House warm-up", "file_paths": ["/Volumes/Music/Artist/Opening.mp3", "/Volumes/Music/Artist/Finale.mp3"]}
```

Both inputs preserve the supplied order and intentional repeats exactly. No
sorting or deduplication happens. The JSON record always saves the resolved
track IDs. File locations you supply become part of the tool input and may be
visible in your Codex conversation; prefer IDs to keep paths local. Neither
success nor error responses return audio paths. Unmatched or ambiguous file
locations are reported by their position in the supplied list.

Optional `separators` entries insert a supplied separator before a 1-based
`before_track` position; use one past the final track to append. Choose `generic`,
`90s`, `R&B`, `Ambi`, `Salsa`, `Party`, or `Dance`. Each fixed WAV file must
exist in the configured separator folder and match exactly one active snapshot
track. The M3U8 and JSON include separators in the requested order, and the JSON
records each separator type.

Exports use the requested playlist name in two repository folders:

- `playlists/House warm-up.m3u8`: UTF-8 playlist containing absolute local
  audio paths.
- `output/House warm-up.json`: playlist name, ordered IDs, creation time and
  format version.

If an export with the requested base name already exists, Codex asks whether
you want to update it or create a separate playlist under a different name.
After you confirm an update, Codex replaces the M3U8 and JSON files at the same
paths. Existing `-vNNN` exports are updated in place under their current names.
To revise a saved selection, ask Codex to read its JSON, adjust the IDs,
validate them against the current snapshot, and export with the update choice.

Track order and intentional repeated IDs are preserved. An export accepts
1–1000 tracks via either input. Every ID must exist and not be marked deleted,
and every referenced audio file must be present. Errors report affected IDs without revealing audio
paths. Nothing is silently skipped and validation failures create no artifacts.

Names must be a single filename stem without slashes or control characters,
up to 200 UTF-8 bytes. Existing files are replaced only after you confirm an
update, and symlink destinations are refused. The destinations are fixed by the
adapter, not chosen by the model.
Exports are ignored by Git. Treat M3U8 files as private because they contain
local filesystem paths.

Open Rekordbox and manually import the M3U8 when you choose. The adapter does
not perform that import. Importing is your explicit action and changes the
Rekordbox collection; generating the export changes no original data.

Before relying on duplicate-free import, test it manually with
three existing tracks: record the collection count and their metadata, import
the generated playlist, then confirm that existing entries were reused, no
duplicates appeared, and BPM, key, cue points and beat grids remain intact.
The application must not perform that import automatically. Duplicate-free
import remains unresolved.

## 6. Update the upstream MCP

Use a separate Terminal window in the repository root. The updater tracks the
latest commit on upstream's default branch, pins that exact revision, and
requires network access. Startup never upgrades dependencies automatically.

**Step 1 — check without installing:**

```sh
uv --directory rekordbx-mcp run --locked rekordbx-mcp update-upstream --check
```

An available update is reported as `Update available: <current> -> <latest>`.
If the installed pin already matches upstream, no changes are made.

**Step 2 — stop the existing MCP connection or close Codex.** Leave the
separate Terminal window open so the upgrade can finish.

**Step 3 — install and test:**

```sh
uv --directory rekordbx-mcp run --locked rekordbx-mcp update-upstream
```

The updater changes the upstream commit pin in `rekordbx-mcp/pyproject.toml`,
updates `uv.lock`, synchronizes dependencies, and runs the full test suite.
Wait for `Updated to upstream commit <commit>; compatibility tests passed.`
before reconnecting.

**Step 4 — restart the MCP connection or reopen Codex.** When Rekordbox is
closed, the updated MCP prepares a fresh verified copy; if it is open, the MCP
uses the newest verified copy already on disk. Ask it to show your library
statistics to confirm the connection.

**Step 5 — keep the tested revision in Git.** After a successful upgrade,
review and commit the changed `rekordbx-mcp/pyproject.toml` and
`rekordbx-mcp/uv.lock` if you want to preserve that revision in the repository.

If a step fails, the updater restores the previous dependency files and attempts to
restore the previous environment. If environment recovery also fails, retry:

```sh
uv --directory rekordbx-mcp sync --locked
```

An incompatible upstream revision is rejected; newly added tools are not
automatically exposed. The update command does not open the original Rekordbox
database or alter your music files.

Routine startup uses the locked dependencies and the existing configuration.
You do not need to copy the configuration template again for a normal upgrade.

## 7. Troubleshooting

| Symptom | What to do |
| --- | --- |
| “Close Rekordbox and its background agents” | Quit Rekordbox and its agents cleanly, then retry the MCP connection. |
| “Cannot verify Rekordbox is closed” | Process inspection was denied or incomplete. Run from a normal macOS terminal to diagnose permissions; do not bypass the check. |
| “Database transaction sidecar exists” | Let Rekordbox finish and quit normally. Do not delete original WAL, SHM or journal files. If they remain, investigate before retrying. |
| Database not found | Check the default source path or supply `--source` after `start`. |
| Offline dependency or interpreter error | Run the setup command with network access before starting the offline MCP connection. |
| Snapshot hash invalid | Close Rekordbox and use `start` to create a fresh verified copy. Do not edit the snapshot or its manifest. |
| MCP tools do not appear | Check project trust, the uv and project paths, and the TOML configuration. Restart the connection after saving. |
| Collection results look old | Quit Rekordbox and restart the MCP to refresh its snapshot. |
| Server waits silently in Terminal | Expected for a stdio MCP server; use it through the configured Codex connection. |

## 8. Tests and file locations

```sh
uv --directory rekordbx-mcp run --locked pytest -q
```

Tests use synthetic encrypted collections. They cover safe startup, copying,
write restrictions, forbidden tools, updates and rollback, and an actual
MCP conversation through the snapshot launcher.

| Location | Purpose |
| --- | --- |
| `rekordbx-mcp/src/rekordbx_mcp/` | Custom adapter, startup, launcher and updater |
| `rekordbx-mcp/tests/` | Automated tests |
| `rekordbx-mcp/codex-mcp.example.toml` | Codex connection template |
| `rekordbx-mcp/.cache/rekordbox-snapshots/` | Generated collection copies |
| `output/` | Generated JSON export plans |
| `playlists/` | Generated M3U8 playlists for manual import |
| `AGENTS.md` | Repository rules, including original-data protection |

More implementation details are in the
[adapter README](../rekordbx-mcp/README.md).

## Privacy and limits

The adapter opens only verified snapshots through a read-only SQLCipher
connection and exposes the approved reading tools plus the local exporter.
The exporter writes new M3U8 files only in `playlists/` and matching JSON files
only in `output/`. The worker runs with normal user filesystem and network
permissions; there is no OS isolation.
Dedicated `file_path` and `database_path` fields are omitted from ordinary responses.
The upstream filepath-returning tools are not exposed. The export tool returns
artifact paths and a track count, not the audio paths inside the M3U8.

Returned track metadata becomes part of the Codex conversation. Running the
database reader locally does not make the AI conversation fully offline.
No audio upload feature is implemented.

CrateDeck is a separate local application. Its explicit **Embed into MP3**
action can write artwork to a playlist-selected MP3 after creating an exact
backup under `output/audio-backups/`; this does not change the Rekordbox database
or the MCP's read-only snapshot. CrateDeck API tests are kept with the app in
`neon-crate/tests/`.

The project does not provide a standalone playlist-generation CLI or automatic
Rekordbox import. JSON records preserve selections for further work in chat.
M3U8 duplicate-free import is still an unresolved manual check. The snapshot
and connection controls are application-level protections, not an OS boundary
against arbitrary filesystem access by dependencies.
