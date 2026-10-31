# Rekordbx MCP

For setup, Codex configuration, everyday playlist requests and troubleshooting,
start with the [complete user guide](../docs/user-guide.md).
For a product overview and quick start, see [Rekordbx](../README.md).

A native macOS adapter for the upstream
[rekordbox-mcp](https://github.com/davehenke/rekordbox-mcp), managed with uv.
It exposes 18 reading tools against a verified copy of the collection.
The original Rekordbox database, playlists, analysis files and audio remain
read-only source data. Docker is not used.

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

Check for an update:

```sh
uv run --locked rekordbx-mcp update-upstream --check
```

Install the latest commit from the upstream repository's default branch:

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
An incompatible upstream release is rejected until the adapter is adjusted;
new upstream tools are never automatically added to the read allowlist.
Startup stays pinned and offline; it does not perform upgrades.

## Start with a fresh safe copy

Quit Rekordbox and its background agents cleanly, then run:

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
JSON playlist persistence and a track-ID-based M3U8 exporter are future work.

## Protection boundaries

- **Source copier:** ordinary binary reads of the original, outside the worker.
  Its only writes are newly created snapshot files outside the source folder.
- **Database connection:** SQLCipher uses an explicit file URI with
  `mode=ro&immutable=1`, query-only mode, and an authorizer blocking attachments
  and PRAGMA changes. Immutable mode is only used after rejecting transaction
  sidecars and verifying the snapshot.
- **MCP registry:** a separate, fixed allowlist registers only the reviewed
  upstream reading functions. New upstream tools are excluded automatically.
  Creation, deletion, imports, cleanup and arbitrary reconnection are absent,
  including when called by name.
- **Privacy:** ordinary tool responses omit file paths and database paths.
  The upstream `get_track_file_path` and `get_genre_filepaths` tools are not
  exposed. A future local exporter can resolve IDs to paths without sending
  those paths to the model.

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
does not infer energy, popularity or danceability, and does not currently verify
missing audio files.

M3U8 export is future work, and verification that Rekordbox reuses existing
entries is still pending. See the
[import verification requirements](../docs/user-guide.md#5-m3u8-import-test).
