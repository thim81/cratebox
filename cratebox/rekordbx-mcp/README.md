# Rekordbox MCP adapter

This project adapts the pinned upstream [`rekordbox-mcp`](https://github.com/davehenke/rekordbox-mcp) to use a verified local snapshot through a read-only SQLCipher connection. It is a consumer-neutral collection data provider; playlist editing, export, Spotify, Sockseek, playback, and artwork behavior belong to CrateBox Core and its API.

The original Rekordbox database, playlists, XML exports, analysis files, metadata, and audio are not modified by this adapter. It runs with normal user permissions; these application-level controls are not OS filesystem or network isolation. Docker is not used.

## Install and run

From the repository root:

```sh
uv --directory cratebox/rekordbx-mcp sync --locked --python 3.12
uv --directory cratebox/rekordbx-mcp run --locked rekordbx-mcp --help
```

The upstream source is pinned in `pyproject.toml`, and the dependency resolution is pinned by `uv.lock`. The adapter imports upstream reading functions without changing the installed upstream files.

For a standalone consumer, use [`codex-mcp.example.toml`](codex-mcp.example.toml) as a starting point. The CrateBox app uses a different configuration: [the repository example](../cratebox-mcp.example.toml) launches CrateBox's same-process REST/MCP service and proxies it over stdio.

To start the adapter manually for diagnostics, close Rekordbox and its background agents, then run:

```sh
uv --directory cratebox/rekordbx-mcp run --locked rekordbx-mcp start
```

When Rekordbox is closed, `start` creates and verifies a fresh snapshot. When Rekordbox is running, it reuses only the newest verified snapshot already on disk; it fails if no valid snapshot is available. It never copies the live database. The worker uses one fixed snapshot path for its lifetime.

Use `snapshot` to create a copy without starting an MCP session:

```sh
uv --directory cratebox/rekordbx-mcp run --locked rekordbx-mcp snapshot
```

Snapshots remain under the existing repository-root `rekordbx-mcp/.cache/rekordbox-snapshots/` location, are ignored by Git, and contain private library metadata. The source is checked before and after copying; transaction sidecars, hash mismatches, and invalid manifests prevent a snapshot from being served.

## Generic collection contract

The adapter registers a fixed set of reviewed upstream reading functions. Newly added upstream tools are excluded until reviewed. The custom `get_collection_tracks` operation supports ordered track IDs, exact absolute file locations, or deterministic pagination over active tracks. It returns generic metadata, technical audio details, cue counts, playlist membership, and local locations for trusted application clients.

The CrateBox API uses locations only inside the local server for matching, playback, and export. Do not add `get_collection_tracks` or other path-returning operations to conversational MCP client allowlists. Public adapter responses redact file and database paths. CrateBox's browser API and conversational MCP tools also omit audio paths.

The adapter does not expose collection mutation, playlist export, Spotify, Sockseek, artwork, or CrateBox-specific matching tools. CrateBox Core owns those behaviors.

## Protection boundaries

- Snapshot creation writes only new copies outside the source folder; it does not change source permissions or links.
- The connection uses an explicit snapshot file URI with `mode=ro&immutable=1`, SQLCipher, query-only mode, and an authorizer that blocks database attachment and PRAGMA changes.
- A process lock serializes use of the shared upstream ORM session and snapshot connection.
- The adapter has a fixed registry of reviewed upstream reading tools. Upstream create, delete, import, cleanup, and arbitrary reconnect functions are unavailable, including when called directly by name.
- `enabled_tools` in a client config is an additional discovery/invocation restriction, not a replacement for the adapter's snapshot and tool protections.

## Update upstream

Check for a new upstream revision without changing the installation:

```sh
uv --directory cratebox/rekordbx-mcp run --locked rekordbx-mcp update-upstream --check
```

For an explicit update, stop active MCP sessions and run:

```sh
uv --directory cratebox/rekordbx-mcp run --locked rekordbx-mcp update-upstream
```

The updater resolves the new revision to an exact commit, updates the pin and lockfile, runs compatibility and safety tests, and rolls back dependency files if an update fails. Review and commit `pyproject.toml` and `uv.lock` only after the update succeeds. New upstream tools are never enabled automatically.

## Tests

```sh
uv --directory cratebox/rekordbx-mcp run --locked pytest -q
```

Tests use synthetic encrypted collections and cover snapshot creation/verification, source preservation, database write restrictions, reconnect restrictions, direct calls to forbidden tools, generic track resolution, and an MCP stdio session through the snapshot launcher.
