"""Keyless music catalogue artwork search adapters."""

import json
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


USER_AGENT = "CrateBox/1.0 (https://github.com/thim/rekordbx)"
_JSON_LIMIT = 2 * 1024 * 1024
_MB_LOCK = threading.Lock()
_LAST_MB_REQUEST = 0.0
_MBID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _https_url(value: object, hosts: tuple[str, ...]) -> bool:
    if not isinstance(value, str) or len(value) > 2048:
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme == "https"
        and not parsed.username
        and not parsed.password
        and port in (None, 443)
        and not parsed.fragment
        and any(host == allowed or host.endswith("." + allowed) for allowed in hosts)
    )


def _secure_provider_url(value: object, hosts: tuple[str, ...]) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    hostname = (parsed.hostname or "").lower()
    trusted_host = any(hostname == allowed or hostname.endswith("." + allowed) for allowed in hosts)
    if parsed.scheme == "http" and trusted_host and port in (None, 80):
        netloc = parsed.netloc.rsplit(":", 1)[0] if port == 80 else parsed.netloc
        value = urlunsplit(("https", netloc, parsed.path, parsed.query, parsed.fragment))
    return value if _https_url(value, hosts) else None


def _get_json(url: str, *, musicbrainz: bool = False, timeout: float = 6) -> dict:
    global _LAST_MB_REQUEST
    if musicbrainz:
        with _MB_LOCK:
            delay = 1.0 - (time.monotonic() - _LAST_MB_REQUEST)
            if delay > 0:
                time.sleep(delay)
            _LAST_MB_REQUEST = time.monotonic()
            return _read_json(url, timeout=timeout)
    return _read_json(url, timeout=timeout)


def _read_json(url: str, *, timeout: float) -> dict:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise ValueError("Provider returned a non-success response")
            data = response.read(_JSON_LIMIT + 1)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        raise ValueError("Artwork provider is unavailable") from None
    if len(data) > _JSON_LIMIT:
        raise ValueError("Artwork provider response is too large")
    try:
        result = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("Artwork provider returned invalid JSON") from None
    if not isinstance(result, dict):
        raise ValueError("Artwork provider returned invalid data")
    return result


def itunes_matches(query: str) -> list[dict[str, str]]:
    """Search song metadata to help identify the right MusicBrainz release."""
    url = "https://itunes.apple.com/search?" + urlencode(
        {"term": query, "entity": "song", "media": "music", "limit": 12}
    )
    payload = _get_json(url)
    results = []
    for item in payload.get("results", []):
        if not isinstance(item, dict):
            continue
        track = str(item.get("trackName", "")).strip()
        album = str(item.get("collectionName", "")).strip()
        artist = str(item.get("artistName", "")).strip()
        if album and artist:
            results.append({"track": track[:300], "album": album[:300], "artist": artist[:300]})
    return results


def _lucene_phrase(value: str) -> str:
    escaped = re.sub(r'([+\-&|!(){}\[\]^"~*?:\\/])', r"\\\1", value.strip())
    return f'"{escaped}"'


def musicbrainz_search(
    query: str, *, artist: str = "", album: str = "", track: str = ""
) -> list[dict[str, str]]:
    """Find release front covers through MusicBrainz and Cover Art Archive."""
    release_name = album.strip() or track.strip() or query.strip()
    lucene = f"release:{_lucene_phrase(release_name)}"
    if artist.strip():
        lucene += f" AND artist:{_lucene_phrase(artist)}"
    search_url = "https://musicbrainz.org/ws/2/release/?" + urlencode(
        {"query": lucene, "fmt": "json", "limit": 6}
    )
    payload = _get_json(search_url, musicbrainz=True)
    results = []
    seen = set()
    for release in payload.get("releases", [])[:3]:
        if not isinstance(release, dict):
            continue
        mbid = str(release.get("id", "")).lower()
        if not _MBID.fullmatch(mbid) or mbid in seen:
            continue
        seen.add(mbid)
        metadata_url = f"https://coverartarchive.org/release/{mbid}"
        try:
            metadata = _get_json(metadata_url, timeout=2)
        except Exception:
            continue
        images = metadata.get("images", [])
        if not isinstance(images, list):
            continue
        fronts = [image for image in images if isinstance(image, dict) and image.get("front") is True]
        fronts.sort(key=lambda image: not bool(image.get("approved")))
        if not fronts:
            continue
        cover = fronts[0]
        allowed_image_hosts = ("coverartarchive.org", "archive.org")
        image_url = _secure_provider_url(cover.get("image", ""), allowed_image_hosts)
        if not image_url:
            continue
        thumbnails = cover.get("thumbnails", {})
        if not isinstance(thumbnails, dict):
            thumbnails = {}
        thumbnail = next(
            (_secure_provider_url(thumbnails.get(size), allowed_image_hosts) for size in ("500", "1200", "250")
             if _secure_provider_url(thumbnails.get(size), allowed_image_hosts)),
            image_url,
        )
        credits = release.get("artist-credit", [])
        artist_name = "".join(
            f"{credit.get('name', '')}{credit.get('joinphrase', '')}"
            for credit in credits if isinstance(credit, dict)
        ).strip() if isinstance(credits, list) else ""
        title = " — ".join(part for part in (str(release.get("title", "")), artist_name) if part)
        results.append({
            "title": title[:300],
            "image_url": image_url,
            "thumbnail_url": thumbnail,
            "source_url": f"https://musicbrainz.org/release/{quote(mbid, safe='')}",
            "source": "Cover Art Archive",
        })
    return results


def search_music_artwork(
    query: str, *, artist: str = "", album: str = "", track: str = ""
) -> list[dict[str, str]]:
    """Try curated music catalogues in preferred order, tolerating provider outages."""
    try:
        matches = itunes_matches(query)
    except Exception:
        matches = []
    if matches:
        match = matches[0]
        try:
            results = musicbrainz_search(
                query,
                artist=match["artist"] or artist,
                album=match["album"],
            )
            if results:
                return results
        except Exception:
            pass
    else:
        try:
            return musicbrainz_search(query, artist=artist, album=album, track=track)
        except Exception:
            return []
    if artist or album:
        if matches and artist == matches[0]["artist"] and album == matches[0]["album"]:
            return []
        try:
            return musicbrainz_search(query, artist=artist, album=album, track=track)
        except Exception:
            return []
    return []
