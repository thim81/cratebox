# Repository instructions

- Custom MCP source, tests, Python project configuration, lockfile, and setup documentation live in `rekordbx-mcp/`. Run uv from that directory, or use `uv --directory rekordbx-mcp ...` from the repository root.

- **Never change or alter the original Rekordbox data.** Treat the live Rekordbox database, playlists, XML exports, analysis files, audio files, and metadata as read-only. Use temporary byte-for-byte copies or exported snapshots for inspection and testing, and write generated artifacts only outside the original Rekordbox data locations.
- Use uv for Python environments, commands, and tests. Use the native macOS launcher; do not use Docker.
- Configure MCP clients to launch `rekordbx-mcp start`: require Rekordbox and its agents to be closed, create and verify a fresh read-only snapshot, then launch the protected MCP. Startup must fail if checking or copying fails; never silently reuse an old snapshot. Keep the OS sandbox and database read-only protections; a client tool allowlist alone is insufficient. Never configure the upstream `rekordbox-mcp` command against the live library.
- Keep upstream unmodified and pinned. Use `rekordbx-mcp update-upstream` for explicit upgrades with compatibility tests and rollback. Upgrading must not automatically expose new tools or weaken the snapshot, sandbox, or read-only database protections.
