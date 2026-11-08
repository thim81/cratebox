# Loaded track rating design

## Intent

Let the user set a 0–5 star rating for the track currently loaded in the CrateBox deck. Persist the rating in the audio file so it applies to CrateBox and Rekordbox tracks without editing Rekordbox's database.

## Approaches

- **Write audio metadata (chosen):** support MP3 and M4A, matching current embedded-artwork write support. Store MP3 ratings in ID3 POPM and M4A ratings in an iTunes-style freeform `RATING` tag. CrateBox reads the embedded rating first and uses its existing crate or collection rating when no file rating exists. M4A rating-tag interoperability may vary between players.
- **CrateBox-only override:** simpler metadata handling, but the rating would not travel with the audio file and would not meet the request.
- **Edit Rekordbox's database:** would update Rekordbox's own rating, but violates the read-only collection boundary.

## Behavior and constraints

- Put an interactive five-star control in the deck for the loaded track; clicking the current rating again clears it to zero.
- Resolve the audio file on the server from the active CrateBox crate or verified Rekordbox playlist membership. Keep file paths out of browser responses.
- Stage, verify, then atomically replace the file; preserve audio data and other tags, and retain no backup. Reject unsupported formats or unsafe files without changing them.
- Return the new rating and update the loaded track and its corresponding tracklist row. Rekordbox's database rating remains unchanged.
- Update `AGENTS.md` to allow only this narrowly scoped rating write in addition to embedded artwork edits.
