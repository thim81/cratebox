import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "neon-crate"))
from api import artwork, music_artwork


def test_itunes_search_normalizes_release_metadata_only(monkeypatch):
    monkeypatch.setattr(
        music_artwork,
        "_get_json",
        lambda url, **_kwargs: {
            "resultCount": 1,
            "results": [{
                "kind": "song",
                "trackName": "Track",
                "artistName": "Artist",
                "collectionName": "Album",
            }],
        },
    )

    results = music_artwork.itunes_matches("Artist Track")

    assert len(results) == 1
    assert results[0] == {"track": "Track", "album": "Album", "artist": "Artist"}
    assert "image_url" not in results[0]


def test_itunes_discards_results_without_release_metadata(monkeypatch):
    monkeypatch.setattr(
        music_artwork,
        "_get_json",
        lambda *_args, **_kwargs: {
            "results": [{"trackName": "Track", "artistName": "Artist"}],
        },
    )

    assert music_artwork.itunes_matches("query") == []


def test_musicbrainz_release_uses_front_cover_and_archive_thumbnail(monkeypatch):
    calls = []
    mbid = "12345678-1234-4234-8234-123456789abc"

    def fake_json(url, **_kwargs):
        calls.append(url)
        if "musicbrainz.org" in url:
            return {
                "releases": [{"id": mbid, "title": "Album", "artist-credit": [{"name": "Artist"}]}],
            }
        return {
            "images": [{
                "front": True,
                "approved": True,
                "image": f"http://coverartarchive.org/release/{mbid}/front.jpg",
                "thumbnails": {"500": f"http://coverartarchive.org/release/{mbid}/front-500.jpg"},
            }],
        }

    monkeypatch.setattr(music_artwork, "_get_json", fake_json)

    results = music_artwork.musicbrainz_search("Artist Track", artist="Artist", album="Album")

    assert len(results) == 1
    assert results[0]["source"] == "Cover Art Archive"
    assert results[0]["image_url"].endswith("front.jpg")
    assert results[0]["thumbnail_url"].endswith("front-500.jpg")
    assert results[0]["source_url"] == f"https://musicbrainz.org/release/{mbid}"
    assert "release%3A%22Album%22" in calls[0]
    assert "artist%3A%22Artist%22" in calls[0]


def test_musicbrainz_caps_cover_archive_checks(monkeypatch):
    checked = []
    releases = [
        {"id": f"12345678-1234-4234-8234-{index:012d}", "title": "Album"}
        for index in range(6)
    ]

    def fake_json(url, **_kwargs):
        if "musicbrainz.org" in url:
            return {"releases": releases}
        checked.append(url)
        raise ValueError("not found")

    monkeypatch.setattr(music_artwork, "_get_json", fake_json)

    assert music_artwork.musicbrainz_search("Album") == []
    assert len(checked) == 3


def test_search_uses_itunes_then_musicbrainz_then_duckduckgo(monkeypatch):
    calls = []
    mb = {"title": "CAA", "image_url": "https://img.example/caa.jpg"}

    def musicbrainz_search(*_args, **kwargs):
        calls.append(("musicbrainz", kwargs))
        return [mb]

    class FakeDDGS:
        def images(self, *_args, **_kwargs):
            calls.append("ddg")
            return [
                {"title": "DuckDuckGo", "image": "https://img.example/ddg.jpg", "thumbnail": "https://img.example/ddg.jpg", "url": "https://source.example"}
            ]

    monkeypatch.setattr(
        music_artwork,
        "itunes_matches",
        lambda *_args: calls.append("itunes") or [{"track": "Track", "album": "Album", "artist": "Artist"}],
    )
    monkeypatch.setattr(music_artwork, "musicbrainz_search", musicbrainz_search)
    monkeypatch.setattr(artwork, "DDGS", FakeDDGS)

    results = artwork.search_image_results("Artist Track", artist="Artist", album="Album")

    assert results[0] == mb
    assert results[1]["source"] == "DuckDuckGo"
    assert calls == ["itunes", ("musicbrainz", {"artist": "Artist", "album": "Album"}), "ddg"]


def test_search_tops_up_catalogue_results_to_twenty_four_distinct_images(monkeypatch):
    catalogue = [
        {"title": "CAA 1", "image_url": "https://images.example/1.jpg", "thumbnail_url": "https://images.example/1.jpg", "source_url": "https://musicbrainz.org/1", "source": "Cover Art Archive"},
        {"title": "CAA 2", "image_url": "https://images.example/2.jpg", "thumbnail_url": "https://images.example/2.jpg", "source_url": "https://musicbrainz.org/2", "source": "Cover Art Archive"},
    ]

    class FakeDDGS:
        def images(self, *_args, **kwargs):
            assert kwargs["max_results"] == 24
            return [
                {"title": "Duplicate", "image": "https://images.example/1.jpg", "thumbnail": "", "url": "https://source.example/duplicate"},
                *[
                    {"title": f"DDG {index}", "image": f"https://images.example/{index}.jpg", "thumbnail": "", "url": f"https://source.example/{index}"}
                    for index in range(2, 25)
                ],
            ]

    monkeypatch.setattr(music_artwork, "search_music_artwork", lambda *_args, **_kwargs: catalogue)
    monkeypatch.setattr(artwork, "DDGS", FakeDDGS)

    results = artwork.search_image_results("Artist Track", artist="Artist", album="Album")

    assert len(results) == 24
    assert results[:2] == catalogue
    assert len({result["image_url"] for result in results}) == 24
    assert results[-1]["source"] == "DuckDuckGo"


def test_search_keeps_catalogue_results_if_duckduckgo_supplement_fails(monkeypatch):
    catalogue = [{"title": "CAA", "image_url": "https://images.example/cover.jpg", "source": "Cover Art Archive"}]

    class BrokenDDGS:
        def images(self, *_args, **_kwargs):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(music_artwork, "search_music_artwork", lambda *_args, **_kwargs: catalogue)
    monkeypatch.setattr(artwork, "DDGS", BrokenDDGS)

    assert artwork.search_image_results("Artist Track") == catalogue


def test_catalogue_uses_track_metadata_when_itunes_has_no_match(monkeypatch):
    calls = []
    monkeypatch.setattr(music_artwork, "itunes_matches", lambda *_args: [])
    monkeypatch.setattr(
        music_artwork,
        "musicbrainz_search",
        lambda query, **kwargs: calls.append((query, kwargs)) or [{"source": "Cover Art Archive"}],
    )

    results = music_artwork.search_music_artwork(
        "Artist Track", artist="Artist", album="Album", track="Track"
    )

    assert results == [{"source": "Cover Art Archive"}]
    assert calls == [("Artist Track", {"artist": "Artist", "album": "Album", "track": "Track"})]


def test_search_falls_back_to_duckduckgo_when_catalogues_are_empty(monkeypatch):
    calls = []
    monkeypatch.setattr(music_artwork, "itunes_matches", lambda *_args, **_kwargs: calls.append("itunes") or [])
    monkeypatch.setattr(music_artwork, "musicbrainz_search", lambda *_args, **_kwargs: calls.append("musicbrainz") or [])

    class FakeDDGS:
        def images(self, *_args, **_kwargs):
            return [{
                "title": "Generic result",
                "image": "https://images.example/one.jpg",
                "thumbnail": "https://thumbs.example/one.jpg",
                "url": "https://source.example/one",
            }]

    monkeypatch.setattr(artwork, "DDGS", FakeDDGS)

    result = artwork.search_image_results("query")

    assert result[0]["source"] == "DuckDuckGo"
    assert calls == ["itunes", "musicbrainz"]


def test_search_continues_after_catalogue_errors(monkeypatch):
    monkeypatch.setattr(music_artwork, "itunes_matches", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(music_artwork, "musicbrainz_search", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError()))

    class FakeDDGS:
        def images(self, *_args, **_kwargs):
            return [{"title": "ok", "image": "https://images.example/one.jpg", "thumbnail": "", "url": "https://source.example"}]

    monkeypatch.setattr(artwork, "DDGS", FakeDDGS)

    assert artwork.search_image_results("query")[0]["source"] == "DuckDuckGo"
