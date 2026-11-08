# Centralize CrateBox implementation ledger

Approved plan: rename application to cratebox; extract Core; minimize protected adapter; host MCP with REST; refresh UI.

Constraints: current checkout; no subagents; upstream unchanged; original collection/audio unchanged.

- Baseline: UI 2 tests pass; build passes. API 31 pass, 5 existing image-search failures (missing playwright/environment-dependent Google fallback).
- Adapter baseline: running.
- Directory renamed; tracked references updated.
- Ruling: implementation and review stay in this agent, overriding skill suggestions to delegate.
- Ruling: preserve API entrypoint and existing Python environment, with no new Python project.

## Handoff before model switch
- User requests switching this chat to GPT-6 Luna; no subagents.
- Rename verified: frontend tests 2/2 and build pass under cratebox/.
- API after rename: same 5 image-search failures, 31 passing, even with playwright installed (Google verification/fallback expectations). No regression from rename established.
- Adapter baseline: 88 pass, 3 existing exporter validation privacy tests fail (framework validation includes supplied input paths).
- `rekordbx-mcp/tests/test_collection_contract.py`: two tests for generic `get_collection_tracks`; both pass with the resolver now committed in `6d32ddf`.
- Core extraction underway: Spotify and Sockseek helpers are moved to `cratebox/core/`; new `core/matching.py` ranks candidates from deterministic 1000-track pages through the generic collection contract. CrateBox's API lookup now uses that Core path instead of the adapter-specific similarity tool; MCP exposes the planned `lookup_similar_tracks` name.
- Same-process FastMCP mount is implemented in `cratebox/api/app.py` at `/mcp/`, with lifespan startup/shutdown integration and playlist/collection/export/Spotify/Sockseek tools. A prior user-run MCP handshake returned the initial six playlist tools. Latest expanded registry still needs integration validation.
- This working stage is uncommitted. Focused Core/resolver tests: 8 passed. Full Rekordbox MCP suite: 90 passed, with the same three pre-existing exporter validation privacy failures noted above. Python compile and `git diff --check` pass.
- Inspectr.dev debugging was attempted. Its connected MCP returned `UNAVAILABLE`: `https://mcps.in-spectr.dev/mcp` responded 404 to the server's SSE probe, so direct client checks remain the available MCP diagnostic until that integration works.
- Remaining: migrate playlist/export and all similarity callers to Core; remove app-specific lookup/export/Spotify/Sockseek from the adapter as callers move; add shared revision refresh; implement idempotent service-start config/launcher; update README/config and recheck app operation/playback.
- Startup/config requirement and Inspectr diagnostic steps are recorded in the approved plan below.
- CrateBox branding: README must explain the name as “CrateBox — A direct, playful nod to Rekordbox, hinting at crate management and track prep.” Update README setup and architecture instructions for the new CrateBox Core/MCP after implementation.
- Startup/config stage requested: update the repository `.codex/config.toml` to use an idempotent CrateBox launcher. At MCP startup, check the local CrateBox UI and API/MCP health endpoints; start only missing services with the existing macOS/uv/npm commands, wait for readiness, and fail with actionable logs if a service cannot start. The HTTP MCP is hosted by the API, so it is not a separate daemon. Preserve already-running services and avoid duplicate listeners. README must document automatic startup and manual commands. Scope defaults to the local development stack already used by `npm run dev:all` (Vite UI on 4444, API/MCP on 8000); no remote exposure.
- MCP debugging/verification: use Inspectr.dev during integration debugging to inspect the CrateBox MCP HTTP handshake, tool discovery, invocation arguments/results and errors. Use it to diagnose client/server behavior alongside direct MCP client checks, and avoid exposing audio paths or other sensitive local data in captured or shared traces.
- Next: continue Core migration from playlist/export responsibilities, then remove adapter tools only after the app no longer depends on them.
- Playlist mutation coordination and refresh stage in progress: Core now owns the shared case-insensitive lock registry used by REST/MCP creation and exports; API exposes an opaque playlist revision that changes on successful writes, external content changes and server restarts; the UI polls every two seconds while visible and on focus, defers during mutation, guards stale responses, retains data on transient failures, and only refreshes playlist data (not the loaded Deck).
- Verification for this stage so far: 10 focused Core/resolver tests pass; frontend tests 2/2 and production build pass; Python modules compile and `git diff --check` passes. The existing Vite config emits its prior `__dirname` warning. API integration could not be run in this shell: the UV cache is outside the writable sandbox; the local API was not listening when checked. The user had previously verified `npm run dev:all` and the MCP handshake.
- Implementation notes from inspection: existing search_tracks caps results at 1000, so generic enumeration is necessary for full-library matching. Existing per-playlist locks need to cover Core export and nested operations without deadlocking. Keep browser URL formatting in REST. Tests monkeypatch api.playlists and api.artwork_data; update unit test targets to Core as helpers move while preserving artwork endpoints.
