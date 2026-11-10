# Direct Rekordbox editing implementation plan

Approved in chat: direct original database access only while Rekordbox and agents are closed; immediate user-triggered playlist editing; no snapshots or Save button. Current checkout, upstream pinned and unmodified, no original-database writes during testing.

1. Update AGENTS.md for direct access and permitted companion-file changes.
2. Implement verified recoverable backups outside the source directory, reusing the 300-second cooldown policy; first mutation always backs up, required failure blocks writes. Test real encrypted recovery.
3. Replace snapshot startup with direct access and process checks. Add generic revision-checked create/rename/add/remove/swap/reorder operations, actual entry IDs, and a single transaction owner. Add move_playlist_track around move_song_in_playlist.
4. Wire API and existing UI controls, authoritative refresh, no automatic mutation retries; local crates stay independent.
5. Verify backend/frontend and embedded browser with synthetic databases; update docs.

Rulings: cold file copies are allowed only with source connections closed and no transaction sidecars; verify with SQLCipher integrity checks and recovery tests. Preserve required playlist XML companion. Reuse upstream cooldown policy rather than its warning-only backup copy. Internal removal commits must not escape the transaction owner.
