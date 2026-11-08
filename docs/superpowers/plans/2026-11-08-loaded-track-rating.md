# Loaded Track Rating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users set the rating of the track loaded in the CrateBox deck by writing an embedded rating tag into its MP3 or M4A file.

**Architecture:** Add shared read support for embedded MP3/M4A ratings and transactional write support beside the existing artwork writer. Add local REST routes that resolve crate tracks from app-owned crate data and Rekordbox tracks through verified playlist membership, then expose a five-star deck control that updates the loaded track and its playlist row.

**Tech Stack:** FastAPI, Mutagen, React, TypeScript, Vitest, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-08-loaded-track-rating-design.md`

## Global Constraints

- “Resolve the audio file on the server from the active CrateBox crate or verified Rekordbox playlist membership. Keep file paths out of browser responses.”
- “Stage, verify, then atomically replace the file; preserve audio data and other tags, and retain no backup. Reject unsupported formats or unsafe files without changing them.”
- “Rekordbox's database rating remains unchanged.”
- “Update `AGENTS.md` to allow only this narrowly scoped rating write in addition to embedded artwork edits.”

## Review Focus

- Missing or malformed rating tags return the current fallback rating — test MP3 and M4A read behavior.
- Invalid ratings and unsafe or unsupported files leave the source unchanged — test validation and transactional writes.
- A track ID outside the supplied playlist cannot resolve to a file — test crate and Rekordbox membership checks.
- The loaded track may differ from the selected row — test the Deck callback targets the loaded identity and updates that row only.
- Tag edits must preserve audio and unrelated metadata — verify staged MP3/M4A content before replacement.

---

### Task 1: Embedded rating read and write

**Files:**
- Create: `cratebox/core/audio_metadata.py`
- Modify: `cratebox/core/crates.py`
- Modify: `cratebox/api/artwork_write.py`
- Test: `cratebox/tests/test_audio_metadata.py`
- Test: `cratebox/tests/test_artwork_write.py`
- Test: `cratebox/tests/test_core_crates.py`

**Interfaces:**
- Produces: `read_embedded_rating(path: Path) -> int | None` for supported MP3/M4A tags; `set_audio_rating(source: Path, rating: int) -> None` for validated staged writes.

- [x] Write tests for MP3 POPM and M4A `RATING` read/write, clearing to zero, preservation of other tags and audio data, invalid rating rejection, and failure leaving original bytes intact.
- [x] Run the focused tests and confirm they fail because the read/write functions are missing.
- [x] Implement the shared rating reader and transactional writer; make crate parsing prefer embedded rating and fall back to the saved plan rating when absent.
- [x] Run focused tests until green.
- [x] Commit: `feat: read and write audio file ratings`

### Task 2: Local rating API and loaded-deck control

**Files:**
- Create: `cratebox/api/ratings.py`
- Modify: `cratebox/api/app.py`
- Modify: `cratebox/api/rekordbox_playlists.py`
- Modify: `cratebox/src/lib/cratebox-api.ts`
- Modify: `cratebox/src/components/Deck.tsx`
- Create: `cratebox/src/components/RatingStars.tsx`
- Modify: `cratebox/src/routes/index.tsx`
- Create: `cratebox/src/lib/track-rating.ts`
- Modify: repository-root `AGENTS.md`
- Test: `cratebox/tests/test_artwork_write.py` or new `cratebox/tests/test_audio_rating_api.py`
- Test: `cratebox/src/components/RatingStars.test.tsx`
- Test: `cratebox/src/lib/track-rating.test.ts`

**Interfaces:**
- Consumes: Task 1 `read_embedded_rating(path)` and `set_audio_rating(source, rating)`.
- Produces: `PUT /api/playlists/{playlist_id}/tracks/{track_id}/rating` and `PUT /api/rekordbox/playlists/{playlist_id}/tracks/{track_id}/rating`, each accepting `{"rating": 0..5}` and returning the saved rating without a path.

- [x] Write failing API tests for accepted rating writes, 0–5 validation, missing/non-member tracks, unsafe files, local-origin checks, and unchanged Rekordbox database data.
- [x] Add a failing frontend test for clicking a Deck star when the loaded track is different from the selected row.
- [x] Implement both local endpoints using existing crate resolution and verified Rekordbox membership, plus the allowed-operation instruction update.
- [x] Add an interactive, keyboard-accessible five-star control to the Deck. Clicking the current rating clears it; successful updates refresh the loaded track and its matching row.
- [x] Run the API suite through uv, the full frontend test suite, lint and build.
- [x] Commit: `feat: rate the loaded track in CrateBox`
