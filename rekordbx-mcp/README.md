# Rekordbx MCP

For setup, Codex configuration, everyday playlist requests and troubleshooting,
start with the [complete user guide](../docs/user-guide.md).
For a product overview and quick start, see [Rekordbx](../README.md).

A native macOS adapter for the upstream
[rekordbox-mcp](https://github.com/davehenke/rekordbox-mcp), managed with uv.
It exposes 19 read-only tools against a verified copy of the collection, plus a
local playlist exporter.
The original Rekordbox database, playlists, analysis files and audio remain
read-only source data. Docker is not used.

CrateDeck can also launch this MCP on the first track lookup through its local
API. Close Rekordbox and its background agents before that first lookup; the
worker uses a fresh verified snapshot and stops when CrateDeck's API shuts down.

## Set up

From the repository root, enter `rekordbx-mcp/` first:

```sh
cd rekordbx-mcp
uv sync --locked --python 3.12
uv run --locked rekordbx-mcp --help
```

The upstream source is pinned to a commit in `pyproject.toml`; `uv.lock` pins
the dependency resolution. The adapter imports upstream reading functions
without editing the installed upstream files. Run our `rekordbx-mcp` command.

## Update upstream

From `rekordbx-mcp/`, check for an update without changing the installation:

```sh
uv run --locked rekordbx-mcp update-upstream --check
```

Stop the current MCP connection or close Codex. In a separate Terminal window,
install the latest commit from the upstream repository's default branch:

```sh
uv run --locked rekordbx-mcp update-upstream
```

Run these from the project directory. The updater resolves upstream HEAD to an
exact commit, changes the revision pin, updates the uv lockfile, synchronizes
dependencies and runs the full test suite, including the read-only connection checks.
If a step fails, it restores the previous dependency files and attempts to
restore the previous environment. An environment recovery failure is reported
explicitly with the command to retry.

Updates require network access. Restart the MCP connection after an accepted update.
Quit Rekordbox and its agents before reconnecting so startup can create a fresh
verified copy. Ask Codex to show your library statistics to verify the connection.
After a successful upgrade, review and commit `pyproject.toml` and `uv.lock`
to preserve the tested revision. The existing Codex configuration remains valid.
An incompatible upstream release is rejected until the adapter is adjusted;
new upstream tools are never automatically added to the read allowlist.
Startup stays pinned and offline; it does not perform upgrades.
See the [step-by-step upgrade guide](../docs/user-guide.md#6-update-the-upstream-mcp).

## Start with a fresh safe copy

Once the Codex configuration is installed, quit Rekordbox and its background
agents, then restart Codex or the MCP connection. Codex automatically runs the
startup command; a separate Terminal process is not required.

For manual diagnostics, run this from `rekordbx-mcp/`:

```sh
uv run --locked rekordbx-mcp start
```

Every start checks that Rekordbox is closed, creates a new copy of the current
`master.db`, checks again after copying, verifies the hashes, marks the copy
read-only, and starts the MCP against that copy. If a check fails or
Rekordbox reopens during copying, startup exits with an error. It never falls
back to an older snapshot or closes Rekordbox for you.

This command runs an MCP stdio server, so it normally runs through Codex's MCP
configuration. Startup diagnostics go to stderr; stdout is reserved for MCP.

## Make a snapshot without starting MCP

Quit Rekordbox and its background agents cleanly, then run:

```sh
uv run --locked rekordbx-mcp snapshot
```

This checks the process list, refuses transaction sidecars, copies source bytes,
checks the source again and verifies matching hashes. It prints a new directory
under `.cache/rekordbox-snapshots/`. Incomplete copies have no valid manifest
and cannot be served. No links or source permission changes are used.
Snapshots contain private library metadata, are ignored by Git, and remain
local until you explicitly remove them.

Rekordbox can be reopened after the copy completes. A running MCP uses its fixed
snapshot; restart the MCP with Rekordbox closed to refresh it. Generated copies
are retained locally so a running session's snapshot is never overwritten.
There is no synchronization back to the original library.

## Connect Codex

Use [codex-mcp.example.toml](codex-mcp.example.toml) as a template for
`.codex/config.toml` in this trusted project, or merge its server table into
your existing Codex configuration. No snapshot ID needs to be configured:
the template runs the fresh-copy startup command. It is not automatically
installed. For project scope, place the configuration in the repository-root
`.codex/config.toml`; the template's `--directory` points to `rekordbx-mcp/`.

The command uses `uv run --locked --offline rekordbx-mcp start` to prepare
the copy and launch the MCP worker against the verified snapshot. Its startup timeout
is 120 seconds to allow copying and verification. Quit Rekordbox before Codex
starts or restarts this MCP; if it was open, close it and retry the connection.

For deliberate use of an older verified snapshot, the lower-level
`uv run --locked rekordbx-mcp serve --snapshot /absolute/snapshot/directory`
command remains available. The configuration template always uses `start`.

Codex documents project MCP configuration and tool allowlists in the
[MCP guide](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) and
[configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).

After restarting the configured MCP connection, try:

> Search my collection for house tracks between 120 and 128 BPM. Propose an
> ordered 60-minute playlist using only returned track IDs, and explain your
> choices. Flag uncertainty about energy or mood.

The MCP supplies search and metadata; Codex makes the conversational proposal.
Once the selection is final, ask Codex to call `export_playlist` with a name
and exactly one ordered list: `track_ids` or `file_paths`. File locations must
be absolute local paths matching exactly one active snapshot track. To place a
separator in the sequence, also pass `separators` entries with a `type` and a
1-based `before_track` position (use one past the last track to append). The
available types are `generic`, `90s`, `R&B`, `Ambi`, `Salsa`, `Party`, and
`Dance`. The exporter resolves each fixed WAV reference from the supplied
separator folder and requires it to match exactly one active snapshot track.
M3U8 files
go in `playlists/`, and matching JSON plans go in `output/`, using the requested
name without an automatic version suffix. If that name already exists, Codex
asks whether to update it or use a different name for a separate playlist. On
confirmation, it calls the tool again with `update_existing=true` to replace the
existing pair at the same paths. Existing numbered exports are updated in place
under their current filename.

It checks every ID and audio file, preserves order and repeats, and refuses
symlink destination directories. Errors identify problematic IDs without
returning audio paths. Unknown or ambiguous locations are identified by input
position. JSON saves an ordered `tracks` array pairing each resolved ID with
its absolute file path. Supplying file paths makes them visible in tool
inputs; IDs keep paths local.

The JSON saves the name, ordered IDs and ID/path pairs, format version and
creation time. The M3U8 contains absolute audio paths for manual
import, so treat it as private. Both destination directories are fixed relative
to this repository's source layout; run the adapter using the documented uv
project installation. No export path argument is exposed to the model. Add
`export_playlist` to an existing client's tool allowlist and restart the MCP to
make the new tool available.

`lookup_similar_tracks_for_cratedeck` is reserved for the local CrateDeck API.
It returns file paths for immediate server-side playback and must stay out of
conversational MCP client allowlists; the API removes paths before responding to
the browser.

## Protection boundaries

- **Source copier:** ordinary binary reads of the original, outside the worker.
  Its only writes are newly created snapshot files outside the source folder.
- **Database connection:** SQLCipher uses an explicit file URI with
  `mode=ro&immutable=1`, query-only mode, and an authorizer blocking attachments
  and PRAGMA changes. Immutable mode is only used after rejecting transaction
  sidecars and verifying the snapshot.
- **MCP registry:** a separate, fixed allowlist registers only the reviewed
  upstream reading functions. New upstream tools are excluded automatically.
  Collection creation, deletion, imports, cleanup and arbitrary reconnection
  are absent, including when called by name. The separately reviewed local
  `export_playlist` tool creates external artifacts and is annotated with
  `readOnlyHint = false`; it cannot change collection data.
- **Privacy:** ordinary tool responses omit file paths and database paths.
  The upstream `get_track_file_path` and `get_genre_filepaths` tools are not
  exposed. The local exporter resolves IDs or file locations through the
  snapshot without returning audio paths to the model. Supplying file locations
  does send those paths as tool input; prefer IDs for privacy. Only artifact
  paths and a track count are returned.

`enabled_tools` is an additional client restriction; it does not open the
database read-only or enforce filesystem permissions. Use the snapshot
launcher even when a client allowlist is present.

The worker uses normal user filesystem and network permissions. Snapshot
validation, SQLCipher read-only mode, the SQL authorizer and the tool registry
provide application-level protection; they are not OS isolation.
Keep the configured `start` command so source checks and copying happen before
the worker is launched.

## Tests

```sh
uv run --locked pytest -q
```

Tests use an encrypted synthetic collection. They cover source preservation,
sidecar rejection, tampered copies, database write restrictions, reconnects,
direct calls to forbidden tools, and an actual MCP stdio conversation through
the snapshot launcher. Direct SQL and ORM-write tests verify that the database
connection refuses mutations independently of file permission bits.

Upstream compatibility limitations are retained: smart playlist membership and
the completeness of metadata follow the upstream implementation. This adapter
does not infer energy, popularity or danceability. Reading tools do not verify
audio availability; the export tool checks selected files before writing.

M3U8 export is implemented; verification that manual Rekordbox import reuses
existing entries is still pending. The adapter never imports automatically. See the
[import verification requirements](../docs/user-guide.md#5-export-and-import-playlists).
