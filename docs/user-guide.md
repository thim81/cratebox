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
- Refresh the collection copy automatically whenever the MCP starts.
- Update the upstream MCP with compatibility tests and rollback.

Playlist proposals are currently made in the Codex conversation. There is no
built-in command yet to save, adjust or export an arbitrary generated playlist.
The included XML scanner can produce a small M3U8 import test; it is not the
finished playlist exporter. Duplicate-free import into Rekordbox remains
unverified.

## 1. Install the dependencies

You need macOS with `/usr/bin/sandbox-exec`, Git, uv, Python 3.12, and Codex
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
  "search_history_sessions"
]
```

This is also available in
[`codex-mcp.example.toml`](../rekordbx-mcp/codex-mcp.example.toml). The template
is not automatically installed. Use `command -v uv` to check the executable
path on another machine.

Project-scoped MCP configuration requires a trusted project. Codex also supports
user-level configuration in `~/.codex/config.toml`; use one scope for this
server to avoid duplicate connections. After saving, restart the MCP connection
or reopen Codex. See the official
[MCP configuration guide](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

The tool allowlist limits what Codex can call. Actual read-only access is
enforced separately by the database connection and the macOS sandbox.
Always launch `rekordbx-mcp start` rather than the upstream
`rekordbox-mcp` command.

## 3. Start a session safely

1. Quit Rekordbox and its background agents cleanly.
2. Open or restart the configured Rekordbox MCP connection in Codex.
3. Wait for the connection to be ready.
4. Ask Codex: **“Use the Rekordbox MCP to show my library statistics.”**
5. Once startup has completed, you may reopen Rekordbox.

At each startup the launcher:

1. Checks that Rekordbox and its agents are closed.
2. Refuses to copy a database with WAL, SHM or journal sidecars present.
3. Creates a new independent copy of the current `master.db`.
4. Rechecks processes, source metadata and hashes after copying.
5. Marks the copy read-only and starts the MCP inside the native sandbox.

If any check fails, the MCP does not start. It never closes Rekordbox for you,
deletes source sidecars, or silently falls back to an older copy.

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
Rekordbox, quit Rekordbox and restart the MCP to obtain a new copy. Copies are
retained locally; they are ignored by Git and consume disk space.

For terminal troubleshooting, you can start the same launcher yourself:

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

The copied catalog can contain references to missing audio files. The restricted
MCP cannot check your audio folders, so a valid track ID does not guarantee that
the file is currently available for playback.

## 5. M3U8 import test

The existing [three-track test playlist](../output/phase1/three-track-test.m3u8)
was generated during Phase 1. Before using it, confirm that its file paths
still exist.

To generate a separate test file from your existing XML export:

```sh
uv --directory rekordbx-mcp run --locked python scripts/phase1_scan.py \
  --xml /Users/thim/Library/Pioneer/rekordbox/rekordbox.xml \
  --output /Users/thim/Sites/rekordbx/output/phase1/readme-test.m3u8 \
  --limit 3
```

This selects the first three XML entries whose files exist. It does not use
your musical prompt or the current database snapshot. The inspected XML export
is older than the live collection, so it is only a fallback for this test.
Choose a new output filename if you want to preserve a previous export.

If you choose to import the test manually in Rekordbox, record the collection
count first. After importing, confirm that existing entries were reused, no
duplicates appeared, and BPM, key, cue points and beat grids are intact.
The application does not perform that import. Full instructions and the
unresolved result are in [Phase 1 findings](phase1-findings.md).

## 6. Update the upstream MCP

Check whether a newer upstream commit is available:

```sh
uv --directory rekordbx-mcp run --locked rekordbx-mcp update-upstream --check
```

Install it and run compatibility tests:

```sh
uv --directory rekordbx-mcp run --locked rekordbx-mcp update-upstream
```

The updater changes the upstream commit pin in `rekordbx-mcp/pyproject.toml`,
updates `uv.lock`, synchronizes dependencies, and runs the full test suite.
If a step fails, it restores the previous dependency files and attempts to
restore the previous environment. If environment recovery also fails, retry:

```sh
uv --directory rekordbx-mcp sync --locked
```

Use a normal macOS terminal where native sandboxing is available. Installation
and updates require network access. An incompatible upstream revision is
rejected; newly added tools are not automatically exposed.

After updating, quit Rekordbox and restart the MCP connection. Routine startup
uses the locked dependencies and does not automatically upgrade them.

## 7. Troubleshooting

| Symptom | What to do |
| --- | --- |
| “Close Rekordbox and its background agents” | Quit Rekordbox and its agents cleanly, then retry the MCP connection. |
| “Cannot verify Rekordbox is closed” | Process inspection was denied or incomplete. Run from a normal macOS terminal to diagnose permissions; do not bypass the check. |
| “Database transaction sidecar exists” | Let Rekordbox finish and quit normally. Do not delete original WAL, SHM or journal files. If they remain, investigate before retrying. |
| Database not found | Check the default source path or supply `--source` after `start`. |
| Offline dependency or interpreter error | Run the setup command with network access before starting the offline MCP connection. |
| “sandbox_apply: Operation not permitted” | The current execution environment may prevent nested sandboxing. Diagnose from a normal macOS terminal; do not switch to an unprotected worker. |
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
MCP conversation through the native sandbox. Native sandbox tests may skip
inside an outer sandbox; run them from a normal macOS terminal to verify them.

| Location | Purpose |
| --- | --- |
| `rekordbx-mcp/src/rekordbx_mcp/` | Custom adapter, startup, sandbox and updater |
| `rekordbx-mcp/tests/` | Automated tests |
| `rekordbx-mcp/codex-mcp.example.toml` | Codex connection template |
| `rekordbx-mcp/.cache/rekordbox-snapshots/` | Generated collection copies |
| `output/` | Generated exports |
| `docs/phase1-findings.md` | Original inspection and manual import procedure |
| `AGENTS.md` | Repository rules, including original-data protection |

More implementation details are in the
[adapter README](../rekordbx-mcp/README.md).

## Privacy and limits

The MCP worker cannot access the original library or audio contents through its
normal sandbox permissions, and its network access is blocked. Dedicated
`file_path` and `database_path` fields are omitted from ordinary responses.
The upstream filepath-returning tools are not exposed.

Returned track metadata becomes part of the Codex conversation. Running the
database reader locally does not make the AI conversation fully offline.
No audio upload feature is implemented.

The project does not yet provide a standalone playlist-generation CLI,
validated playlist persistence, or an exporter for arbitrary proposals.
M3U8 duplicate-free import is still an unresolved manual check. The sandbox
and read-only connection provide practical protections, not a formal guarantee
against operating-system or dependency vulnerabilities.
