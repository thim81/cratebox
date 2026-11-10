# Direct Rekordbox editing implementation plan

Approved in chat: direct original database access only while Rekordbox and agents are closed; immediate user-triggered playlist editing; no snapshots or Save button. Current checkout, upstream pinned and unmodified, no original-database writes during testing.

1. Update AGENTS.md for direct access and permitted companion-file changes.
2. Implement verified recoverable backups outside the source directory, reusing the 300-second cooldown policy; first mutation always backs up, required failure blocks writes. Test real encrypted recovery.
3. Replace snapshot startup with direct access and process checks. Add generic revision-checked create/rename/add/remove/swap/reorder operations, actual entry IDs, and a single transaction owner. Add move_playlist_track around move_song_in_playlist.
4. Wire API and existing UI controls, authoritative refresh, no automatic mutation retries; local crates stay independent.
5. Verify backend/frontend and embedded browser with synthetic databases; update docs.

Rulings: cold file copies are allowed only with source connections closed and no transaction sidecars; verify with SQLCipher integrity checks and recovery tests. Preserve required playlist XML companion. Reuse upstream cooldown policy rather than its warning-only backup copy. Internal removal commits must not escape the transaction owner.

## Implementation verification

- MCP suite: 57 tests passed, including actual SQLCipher writes/restores, duplicate identities, tombstoned entries, agent-start checks at commit, missing-file recovery, and XML companion failure recovery.
- API/Core suite: 102 tests passed.
- Frontend: 15 tests passed; production build and lint passed (existing fast-refresh warnings).
- Strict TypeScript check: the same 20 diagnostics as the pre-UI-change HEAD, confirmed by checking an archived baseline; no new diagnostics. Existing errors remain outside this change.
- Embedded browser: verified create, rename, remove, add to an empty playlist, drag reorder, and replace with duplicate track occurrences against the synthetic API on port 8017.
- All database development writes, backup creation and restores used synthetic encrypted databases in temporary folders. No mutations or recovery tests were run against the user's original Rekordbox collection.
- Explicit offline inspection helpers remain for compatibility; normal startup does not create or reuse snapshots.
