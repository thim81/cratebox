"""Spotify playlist parsing for CrateBox."""

import json
import re
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class _SpotifyDataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.capture = False
        self.data = ""

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("id") == "__NEXT_DATA__":
            self.capture = True

    def handle_data(self, data):
        if self.capture:
            self.data += data

    def handle_endtag(self, tag):
        if tag == "script":
            self.capture = False


def spotify_tracklist(url: str) -> list[str]:
    match = re.fullmatch(r"https?://open\.spotify\.com/playlist/([a-zA-Z0-9]+)(?:[/?#].*)?", url.strip())
    if not match:
        raise ValueError("Provide a valid open.spotify.com playlist URL.")
    request = Request(
        f"https://open.spotify.com/embed/playlist/{match.group(1)}",
        headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            html = response.read().decode("utf-8")
    except HTTPError as error:
        raise ValueError(f"Spotify rejected the playlist request (HTTP {error.code}).") from None
    except URLError:
        raise ValueError("Could not reach Spotify; check network access from the CrateBox process.") from None
    parser = _SpotifyDataParser()
    parser.feed(html)
    if not parser.data:
        raise ValueError("Playlist metadata was not present in Spotify's response")
    try:
        tracks = json.loads(parser.data)["props"]["pageProps"]["state"]["data"]["entity"]["trackList"]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise ValueError("Spotify's playlist metadata format was not recognized") from None
    result = []
    for i, track in enumerate(tracks, 1):
        artists = track.get("artists")
        if isinstance(artists, list):
            names = [a if isinstance(a, str) else a.get("name") for a in artists if isinstance(a, (str, dict))]
            names = [name for name in names if name]
        elif isinstance(artists, str):
            names = [artists]
        else:
            names = []
        if not names and isinstance(track.get("subtitle"), str):
            names = [track["subtitle"]]
        title = track.get("title")
        if not isinstance(title, str) or not title or not names:
            raise ValueError("Spotify's playlist metadata is missing track titles or artists")
        result.append(f"{i:02d}. {', '.join(names)} - {title}")
    return result
