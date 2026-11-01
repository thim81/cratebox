
## Architecture
- wavesurfer.js is dynamically imported inside Deck useEffect — it touches the DOM at import, so keep it out of SSR.
- Mock data and the FastAPI reference snippet live in src/lib/crate-data.ts; API mode fetches the same Playlist/Track shape from the configured URL.
