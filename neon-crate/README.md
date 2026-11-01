# CrateDeck local playlist API

The app can read `.m3u` and `.m3u8` playlists through a small local FastAPI server.
The server reads playlists and audio metadata without changing those files.

From this folder, run:

```sh
uv run --with fastapi --with uvicorn --with mutagen uvicorn server:app --port 8000
```

By default, playlists are read from `~/Music/Playlists`. To use another folder:

```sh
PLAYLIST_DIR="/absolute/path/to/playlists" uv run --with fastapi --with uvicorn --with mutagen uvicorn server:app --port 8000
```

Then set the app's API URL to `http://localhost:8000` and enable API mode.
The server provides `GET /api/playlists`, `GET /api/playlists/{playlist_id}`,
and `GET /api/stream?playlist_id=...&track_id=...`. Audio streaming is restricted
to files referenced by playlists in the configured folder.
