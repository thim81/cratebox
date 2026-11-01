# Rekordbx

**Your Rekordbox collection, in conversation.**

Search the music you own, rediscover tracks in your library, and build playlist
proposals with Codex, then export them for manual import. Rekordbx connects your
existing Rekordbox collection to AI through a local MCP server that keeps
collection data read-only.

**macOS · Python 3.12 · uv · 18 collection tools + playlist export**

[Quick start](#quick-start) · [User guide](docs/user-guide.md) ·
[Starting the server](#3-start-through-codex) ·
[Configuration](rekordbx-mcp/codex-mcp.example.toml) ·
[Technical details](rekordbx-mcp/README.md)

> “Build a 90-minute après-ski set from my collection, with Belgian classics,
> recognizable singalongs, and an energetic finale.”

## What you can do

- **Find the right tracks.** Search by artist, title, genre, BPM, and musical key.
- **Explore your taste.** Browse existing playlists, ratings, play counts, and DJ history.
- **Shape a set in conversation.** Ask Codex to select tracks, explain the order,
  estimate duration, and refine the proposal.
- **Keep selections grounded.** Validate proposed track IDs against your collection snapshot.
- **Export your set.** Create an M3U8 playlist in `playlists/` and a matching
  JSON record in `output/`, ready for you to import manually. Choose whether to
  update an existing playlist or save a separate one under a new name.
- **Stay current.** Create a fresh collection copy at startup and update the
  upstream MCP with one command.

Refine proposals in chat, then ask Codex to export the final selection.
The adapter never imports playlists into Rekordbox automatically.

## Quick start

### 1. Install

You need macOS, Git, [uv](https://docs.astral.sh/uv/),
and Codex. Run these commands from the repository root:

```sh
uv --directory rekordbx-mcp sync --locked --python 3.12
uv --directory rekordbx-mcp run --locked rekordbx-mcp --help
```

uv creates the Python environment inside `rekordbx-mcp/.venv/`. No separate
OpenAI API key is needed for the adapter; Codex provides the AI conversation.

### 2. Connect Codex

Open this repository as a trusted local project in Codex. Copy the
[configuration template](rekordbx-mcp/codex-mcp.example.toml) into the
repository's `.codex/config.toml`:

```sh
mkdir -p .codex
cp -n rekordbx-mcp/codex-mcp.example.toml .codex/config.toml
```

If the configuration file already exists, merge the template's server table
into it; the command above leaves existing files untouched. Check that the
template's absolute project path and uv executable path match your machine.

See the [setup guide](docs/user-guide.md#2-configure-codex) for the complete
configuration and troubleshooting.

### 3. Start through Codex

**Codex starts the server automatically when it initializes the configured MCP
connection. You do not need to run a separate server in Terminal.**

1. Quit Rekordbox and its background agents.
2. Restart Codex or restart the Rekordbox MCP connection with this project open.
3. Codex runs `rekordbx-mcp start`, checks that Rekordbox is closed, creates a
   fresh verified read-only copy, and starts the MCP worker.
4. Confirm that the connection is working by asking:

> Use the Rekordbox MCP to show my library statistics.

Once the connection is ready, you may reopen Rekordbox. To refresh the copied
collection later, quit Rekordbox and restart the MCP connection.

**Manual startup is only needed for diagnostics.** From the repository root:

```sh
uv --directory rekordbx-mcp run --locked rekordbx-mcp start
```

This terminal process waits for an MCP client over stdin/stdout; it does not
open an interactive playlist prompt. Press Ctrl+C to stop it. The configured
Codex connection launches its own process rather than attaching to this one.

### 4. Ask for your first playlist

In the connected Codex chat, try:

> Search my collection for house tracks between 120 and 128 BPM.
> Propose a 60-minute playlist using only returned track IDs, validate
> the final selection, and show BPM, key, duration, and selection reasons.

Keep refining in the same chat:

> Replace the opening three tracks with a gentler warm-up and build
> toward a more energetic finish.

More examples are in the [playlist guide](docs/user-guide.md#4-ask-for-playlists).

### 5. Export your playlist

> Export the final selection with `export_playlist`, named "House warm-up",
> preserving the agreed track order. Give me links to the M3U8 and JSON files.

The M3U8 appears in `playlists/`; its matching JSON plan appears in `output/`.
The exporter uses the requested name as-is, without adding a version suffix.
It resolves audio paths locally from the current snapshot and checks that every
selected file exists. Unknown/deleted IDs, missing files, and unsafe names stop
the export. If that name already exists, Codex asks whether to update it or use
a different name for a separate playlist. Updating replaces the M3U8 and JSON
pair at the same paths; older `-vNNN` exports are updated in place under their
existing filename.

Use either an ordered `track_ids` list or an ordered `file_paths` list. File
locations must be absolute local paths matching exactly one active track in the
snapshot. Both options preserve your order and intentional repeats. JSON always
saves ordered ID/path pairs in the JSON plan. Prefer IDs
when you want to keep audio paths out of tool inputs; neither option returns
audio paths in the tool response.

If you configured Codex before this feature was added, add `"export_playlist"`
to `enabled_tools` in `.codex/config.toml`, then restart the MCP with Rekordbox
closed. The updated [template](rekordbx-mcp/codex-mcp.example.toml) includes it.

Import the M3U8 yourself in Rekordbox when ready. This manual import changes your
collection; duplicate-free reuse of existing tracks still needs verification.
See the [export and import guide](docs/user-guide.md#5-export-and-import-playlists).

## Your library stays yours

**Rekordbx treats all original Rekordbox data as read-only.**

Before serving a collection, it checks that Rekordbox is closed, creates an
independent copy of `master.db`, verifies the copy, and marks it read-only.
The MCP worker opens only that verified snapshot through the adapter's read-only
SQLCipher connection. Database mutation and import tools are excluded.

If checking or copying fails, startup stops. A running session keeps its fixed
snapshot; quit Rekordbox and restart the MCP whenever you want to refresh it.
The adapter does not edit existing playlists, analysis files, audio, or tags.
Its export tool creates only new M3U8 files in `playlists/` and JSON plans in
`output/`.

The database reader runs locally. Returned metadata becomes part of your Codex
conversation; the AI conversation is not fully offline. The worker uses your
normal user permissions, without OS filesystem or network isolation.
No audio upload feature is implemented.

Read about the [protection boundaries](rekordbx-mcp/README.md#protection-boundaries)
and [privacy limits](docs/user-guide.md#privacy-and-limits).

## Updates

Upgrades are explicit: Codex startup uses the pinned dependency and does not
automatically install upstream changes. The updater installs the latest commit
from the upstream repository's default branch.

### 1. Check for an update

Open a separate Terminal window in this repository's root directory and run:

```sh
uv --directory rekordbx-mcp run --locked rekordbx-mcp update-upstream --check
```

This reports either the current commit or an available update without changing
your installation. Network access is required.

### 2. Install and test

Stop the Rekordbox MCP connection, or close Codex, before installing. Keep
the separate Terminal window open and run:

```sh
uv --directory rekordbx-mcp run --locked rekordbx-mcp update-upstream
```

The updater refreshes the commit pin, lockfile, and Python environment, then
runs the full compatibility test suite. Wait for the success message before
reconnecting. If already up to date, it leaves the installation unchanged.

### 3. Restart and verify

Quit Rekordbox and its background agents, then reopen Codex or restart the MCP
connection. Codex automatically creates a fresh collection copy and launches
the updated MCP. Confirm it works by asking:

> Use the Rekordbox MCP to show my library statistics.

After a successful upgrade, commit the changed `rekordbx-mcp/pyproject.toml`
and `rekordbx-mcp/uv.lock` if you want the repository to retain the tested revision.

If an upgrade fails, the updater restores the previous dependency files and
attempts to restore the previous environment. If that recovery also fails, run:

```sh
uv --directory rekordbx-mcp sync --locked
```

The updater changes project dependencies; it does not open or modify your
original Rekordbox data. See the
[update guide](docs/user-guide.md#6-update-the-upstream-mcp) for details.

## Project status

Rekordbx currently supports collection search, library exploration, and
conversational playlist proposals. Energy and mood are musical judgments,
not measured audio features. A valid track ID does not guarantee its audio
file is currently available.

Ordered selections can be saved as JSON and exported as M3U8. The JSON contains
track IDs paired with audio paths; the M3U8 also contains local audio paths.
Keep exports private. Duplicate-free Rekordbox import remains unverified.
[Import verification requirements](docs/user-guide.md#5-export-and-import-playlists).

## Development

Custom source, tests, project configuration, and the dependency lockfile live
under `rekordbx-mcp/`. Run the test suite from the repository root:

```sh
uv --directory rekordbx-mcp run --locked pytest -q
```

Tests use synthetic encrypted collections and cover startup, write restrictions,
MCP tool access, database connection restrictions, and update recovery. See the
[adapter documentation](rekordbx-mcp/README.md) for implementation details.

## Built on

Rekordbx reuses [Dave Henke's rekordbox-mcp](https://github.com/davehenke/rekordbox-mcp)
and [pyrekordbox](https://github.com/dylanljones/pyrekordbox).
The upstream MCP is pinned and remains unmodified; the custom adapter supplies
snapshot handling and access restrictions.

This is an independent project and is not affiliated with AlphaTheta.
