## Architecture

- wavesurfer.js is dynamically imported inside Deck useEffect — it touches the DOM at import, so keep it out of SSR.
- Playlist and track data are fetched from the local API URL configured in the app settings.
- Keep `server.py` as the `server:app` launcher entry point; organize FastAPI setup, collection, playlists, artwork, and streaming implementation in `api/` modules.
