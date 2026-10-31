# Rekordbx

**Your Rekordbox collection, in conversation.**

Search the music you own, rediscover tracks in your library, and build playlist
proposals with Codex. Rekordbx connects your existing Rekordbox collection to
AI through a local, read-only MCP server.

**macOS · Python 3.12 · uv · 18 collection tools**

[Quick start](#quick-start) · [User guide](docs/user-guide.md) ·
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
- **Stay current.** Create a fresh collection copy at startup and update the
  upstream MCP with one command.

Playlist proposals currently live in the Codex conversation. A built-in
workflow for saving and exporting arbitrary proposals is still in development.

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

**Quit Rekordbox and its background agents**, then restart Codex or the MCP
connection. Codex launches the server and prepares a fresh snapshot automatically.
You can reopen Rekordbox once the connection is ready.

See the [setup guide](docs/user-guide.md#2-configure-codex) for the complete
configuration and troubleshooting.

### 3. Ask for your first playlist

First, confirm the connection:

> Use the Rekordbox MCP to show my library statistics.

Then try:

> Search my collection for house tracks between 120 and 128 BPM.
> Propose a 60-minute playlist using only returned track IDs, validate
> the final selection, and show BPM, key, duration, and selection reasons.

Keep refining in the same chat:

> Replace the opening three tracks with a gentler warm-up and build
> toward a more energetic finish.

More examples are in the [playlist guide](docs/user-guide.md#4-ask-for-playlists).

## Your library stays yours

**Rekordbx treats all original Rekordbox data as read-only.**

Before serving a collection, it checks that Rekordbox is closed, creates an
independent copy of `master.db`, verifies the copy, and marks it read-only.
The MCP worker opens only that verified snapshot through the adapter's read-only
SQLCipher connection. Database mutation and import tools are excluded.

If checking or copying fails, startup stops. A running session keeps its fixed
snapshot; quit Rekordbox and restart the MCP whenever you want to refresh it.
The adapter does not edit existing playlists, analysis files, audio, or tags.

The database reader runs locally. Returned metadata becomes part of your Codex
conversation; the AI conversation is not fully offline. The worker uses your
normal user permissions, without OS filesystem or network isolation.
No audio upload feature is implemented.

Read about the [protection boundaries](rekordbx-mcp/README.md#protection-boundaries)
and [privacy limits](docs/user-guide.md#privacy-and-limits).

## Updates

Check for a newer upstream MCP revision:

```sh
uv --directory rekordbx-mcp run --locked rekordbx-mcp update-upstream --check
```

Install it and run compatibility tests:

```sh
uv --directory rekordbx-mcp run --locked rekordbx-mcp update-upstream
```

Failed updates restore the previous dependency files and attempt to restore the
previous environment. Routine MCP startup remains pinned and offline.
See the [update guide](docs/user-guide.md#6-update-the-upstream-mcp) for details.

## Project status

Rekordbx currently supports collection search, library exploration, and
conversational playlist proposals. Energy and mood are musical judgments,
not measured audio features. A valid track ID does not guarantee its audio
file is currently available.

Built-in playlist persistence and M3U8 export for arbitrary proposals are
planned. Duplicate-free Rekordbox import remains unverified.
[Import verification requirements](docs/user-guide.md#5-m3u8-import-test).

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
