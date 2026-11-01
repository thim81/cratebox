# CrateDeck local playlist API

The app reads `.m3u` and `.m3u8` playlists through a small local FastAPI server.
In the repository's `playlists/` folder, tracks can be removed from a playlist;
the audio file is never deleted. Other configured playlist folders remain read-only.

From this folder, run:

```sh
uv run --with fastapi --with uvicorn --with mutagen uvicorn server:app --port 8000 --reload
```

By default, playlists are read from the repository root `playlists/` folder. To use another folder:

```sh
PLAYLIST_DIR="/absolute/path/to/playlists" uv run --with fastapi --with uvicorn --with mutagen uvicorn server:app --port 8000 --reload
```

Then set the app's API URL to `http://localhost:8000` and enable API mode.
The server provides `GET /api/playlists`, `GET /api/playlists/{playlist_id}`,
and `GET /api/stream?playlist_id=...&track_id=...`. Audio streaming is restricted
to files referenced by playlists in the configured folder. Track removal uses
`DELETE /api/playlists/{playlist_id}/tracks` with a JSON `track_ids` list and
only works with the repository's `playlists/` folder.
