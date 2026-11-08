import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import matching, revision, sockseek, spotify
import asyncio


def test_spotify_tracklist_parses_ordered_tracks(monkeypatch):
    payload = {
        "props": {"pageProps": {"state": {"data": {"entity": {
            "trackList": [
                {"artists": [{"name": "Artist"}], "title": "First"},
                {"artists": ["Guest"], "title": "Second"},
            ],
        }}}}},
    }
    html = f'<script id="__NEXT_DATA__">{json.dumps(payload)}</script>'
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self): return html.encode()
    monkeypatch.setattr(spotify, "urlopen", lambda *_args, **_kwargs: Response())
    assert spotify.spotify_tracklist("https://open.spotify.com/playlist/abc") == [
        "01. Artist - First", "02. Guest - Second",
    ]


def test_spotify_rejects_non_playlist_url():
    with pytest.raises(ValueError, match="valid open.spotify.com"):
        spotify.spotify_tracklist("https://example.com/playlist/abc")


def test_sockseek_writes_under_repository_root(tmp_path, monkeypatch):
    monkeypatch.setattr(sockseek, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(sockseek, "SOCKSEEK_EXECUTABLE", tmp_path / "sockseek" / "sockseek")
    result = sockseek.create_sockseek_list("warmup", [{"artist": "Artist", "title": "Track"}])
    list_file = tmp_path / result["list_path"]
    assert list_file.read_text().strip() == 's:"Artist - Track"'
    assert result["run_from"] == str(tmp_path)
    assert Path(result["list_path"]).is_relative_to(Path("downloads"))


def test_rank_matches_prefers_normalized_exact_title_then_rating():
    candidates = [
        {"id": "fuzzy", "title": "Bright Light (Extended Mix)", "artist": "A & B", "rating": 5},
        {"id": "exact-low", "title": "Bright Lights", "artist": "A feat. B", "rating": 3},
        {"id": "exact-high", "title": "Bright Lights", "artist": "A feat. B", "rating": 5},
    ]
    ranked = matching.rank_matches("A, B", "Bright Lights (Radio Edit)", candidates, limit=2)
    assert [item[1]["id"] for item in ranked] == ["exact-high", "exact-low"]


def test_rank_matches_rejects_empty_query_and_invalid_limit():
    with pytest.raises(ValueError, match="artist, title"):
        matching.rank_matches(" ", " ", [], limit=5)
    with pytest.raises(ValueError, match="Limit"):
        matching.rank_matches("Artist", "Track", [], limit=51)


def test_lookup_matches_enumerates_collection_pages():
    calls = []
    async def fetch_page(offset, limit):
        calls.append((offset, limit))
        if offset == 0:
            return [{"id": str(index), "artist": "Other", "title": "Other"} for index in range(1000)]
        return [{"id": "1", "artist": "Artist", "title": "Track", "rating": 4}]
    result = asyncio.run(matching.lookup_matches(fetch_page, "Artist", "Track", limit=10))
    assert result[0][1]["id"] == "1"
    assert calls == [(0, 1000), (1000, 1000)]


def test_playlist_revision_changes_after_writes_and_external_edits(tmp_path):
    playlists = tmp_path / "playlists"
    plans = tmp_path / "output"
    playlists.mkdir()
    plans.mkdir()
    tracker = revision.PlaylistRevision(playlists, plans)
    initial = tracker.value()
    (playlists / "Mix.m3u8").write_text("#EXTM3U\n")
    (plans / "Mix.json").write_text('{"tracks":[]}\n')
    externally_changed = tracker.value()
    assert externally_changed != initial
    tracker.mark_written()
    assert tracker.value() != externally_changed
    assert revision.PlaylistRevision(playlists, plans).value() != tracker.value()
