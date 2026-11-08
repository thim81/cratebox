"""Artist/title normalization and ranking for CrateBox collection lookups."""

import re
import unicodedata
from collections.abc import Awaitable, Callable
from difflib import SequenceMatcher

_TRANSLITERATION = str.maketrans({
    "æ": "ae", "œ": "oe", "ø": "o", "ł": "l", "đ": "d",
    "ð": "d", "þ": "th", "ħ": "h", "ı": "i",
})
_ARTIST_SEPARATOR = re.compile(r"\s*(?:[,;&]|\b(?:feat(?:uring)?|ft)\.?|\bx\b)\s*", re.I)
_TITLE_VERSION_MARKERS = {
    "acapella", "club", "clean", "dirty", "edit", "extended", "intro",
    "instrumental", "live", "mashup", "mix", "outro", "radio", "remix",
    "transition", "version", "vip",
}
_TITLE_VERSION_SUFFIXES = (
    "extended remix", "extended mix", "radio edit", "intro edit", "outro edit",
    "quick edit", "short edit", "extended", "instrumental", "acapella",
    "transition", "mashup", "bootleg", "rework", "remix", "version", "clean",
    "dirty", "radio", "intro", "outro", "edit", "mix", "club", "live", "vip",
)


def normalize_match_text(value: str) -> str:
    value = value.casefold().translate(_TRANSLITERATION)
    decomposed = unicodedata.normalize("NFKD", value)
    unaccented = "".join(char for char in decomposed if not unicodedata.combining(char))
    words = "".join(char if char.isalnum() else " " for char in unaccented)
    return " ".join(words.split())


def artist_credits(value: str) -> set[str]:
    return {
        normalized for credit in _ARTIST_SEPARATOR.split(value)
        if (normalized := normalize_match_text(credit))
    }


def normalize_track_title(value: str) -> str:
    original = normalize_match_text(value)
    while match := re.search(r"\s*[\[(]([^\])]+)[\])]\s*$", value):
        suffix = normalize_match_text(match.group(1))
        if not _TITLE_VERSION_MARKERS.intersection(suffix.split()):
            break
        value = value[:match.start()]
    normalized = normalize_match_text(value)
    while normalized:
        suffix = next((item for item in _TITLE_VERSION_SUFFIXES if normalized.endswith(f" {item}")), None)
        if suffix is None:
            break
        normalized = normalized[: -(len(suffix) + 1)]
    return normalized or original


def _similarity(left: str, right: str) -> float:
    normalized_left = normalize_match_text(left)
    normalized_right = normalize_match_text(right)
    if not normalized_left or not normalized_right:
        return 0.0
    sequence_score = SequenceMatcher(None, normalized_left, normalized_right).ratio()
    left_words, right_words = set(normalized_left.split()), set(normalized_right.split())
    token_score = 2 * len(left_words & right_words) / (len(left_words) + len(right_words))
    return max(sequence_score, token_score)


def rank_matches(artist: str, title: str, candidates: list[dict], *, limit: int = 50) -> list[tuple[float, dict]]:
    artist = artist.strip()
    title = title.strip()
    if not artist and not title:
        raise ValueError("Provide an artist, title, or both for collection lookup.")
    if not 1 <= limit <= 50:
        raise ValueError("Limit must be between 1 and 50.")

    source_artists = artist_credits(artist) if artist else set()
    source_title = normalize_track_title(title) if title else ""
    ranked = []
    for source in candidates:
        candidate = dict(source)
        candidate_artists = artist_credits(str(candidate.get("artist") or ""))
        artist_pairs = [
            (left, right) for left in source_artists for right in candidate_artists
            if left in right or right in left
        ]
        if source_artists and not artist_pairs:
            continue
        artist_score = max((_similarity(left, right) for left, right in artist_pairs), default=0)
        candidate_title = normalize_track_title(str(candidate.get("title") or ""))
        exact_title = bool(source_title) and source_title == candidate_title
        title_score = _similarity(source_title, candidate_title) if source_title else 0
        score = (
            (0.35 * artist_score if source_artists else 0)
            + (0.65 * title_score if source_title else 0)
        ) / (0.35 * bool(source_artists) + 0.65 * bool(source_title))
        candidate["_exact_title"] = exact_title
        ranked.append((score, candidate))

    groups: dict[tuple[int, float, int, int], list[tuple[float, dict]]] = {}
    for score, candidate in ranked:
        group = (
            int(candidate.pop("_exact_title", False)), score,
            int(candidate.get("rating") or 0), int(candidate.get("play_count") or 0),
        )
        groups.setdefault(group, []).append((score, candidate))
    ordered = []
    for group in sorted(groups, reverse=True):
        matches = groups[group]
        for field in ("bit_depth", "sample_rate", "bitrate"):
            if all(int(candidate.get(field) or 0) > 0 for _, candidate in matches):
                matches.sort(key=lambda item: int(item[1][field]), reverse=True)
        ordered.extend(matches)
    return ordered[:limit]


async def lookup_matches(
    fetch_page: Callable[[int, int], Awaitable[list[dict]]],
    artist: str,
    title: str,
    *,
    limit: int = 50,
) -> list[tuple[float, dict]]:
    """Rank candidates from deterministic pages of the generic collection contract."""
    if not artist.strip() and not title.strip():
        raise ValueError("Provide an artist, title, or both for collection lookup.")
    if not 1 <= limit <= 50:
        raise ValueError("Limit must be between 1 and 50.")
    page_size = 1000
    offset = 0
    candidates = []
    while True:
        page = await fetch_page(offset, page_size)
        if not isinstance(page, list) or any(not isinstance(item, dict) for item in page):
            raise ValueError("Unexpected collection track page.")
        candidates.extend(page)
        offset += len(page)
        if len(page) < page_size:
            break
    return rank_matches(artist, title, candidates, limit=limit)
