# Repository instructions

- Custom MCP source, tests, Python project configuration, lockfile, and setup documentation live in `rekordbx-mcp/`. Run uv from that directory, or use `uv --directory rekordbx-mcp ...` from the repository root.

- **Never change or alter the original Rekordbox data.** Treat the live Rekordbox database, playlists, XML exports, analysis files, audio files, and metadata as read-only. Use temporary byte-for-byte copies or exported snapshots for inspection and testing, and write generated artifacts only outside the original Rekordbox data locations.
- Use uv for Python environments, commands, and tests. Use the native macOS launcher; do not use Docker.
- Configure MCP clients to launch `rekordbx-mcp start`: require Rekordbox and its agents to be closed, create and verify a fresh read-only snapshot, then launch the MCP against that copy. Startup must fail if checking or copying fails; never silently reuse an old snapshot. Keep the explicit snapshot path, read-only connection, SQL authorizer and tool allowlist. The worker uses normal user permissions; do not claim OS filesystem or network isolation.
- Keep upstream unmodified and pinned. Use `rekordbx-mcp update-upstream` for explicit upgrades with compatibility tests and rollback. Upgrading must not automatically expose new tools or weaken the snapshot or read-only database protections.
- Playlist export resolves ordered track IDs only through the verified snapshot. Write new M3U8 and JSON artifacts only in the repository's `output/` directory; never overwrite files, follow an output-directory symlink, import into Rekordbox, or return audio paths in tool responses. The exporter creates external files, so its MCP annotation must not claim it is read-only.
