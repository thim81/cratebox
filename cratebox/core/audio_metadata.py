"""Read ratings embedded in supported audio files."""

from pathlib import Path

from mutagen import MutagenError
from mutagen.id3 import ID3
from mutagen.mp4 import MP4


def _rating_value(value: object) -> int | None:
    try:
        rating = int(value)
    except (TypeError, ValueError, UnicodeError):
        return None
    return rating if 0 <= rating <= 5 else None


def read_embedded_rating(path: Path) -> int | None:
    """Return the CrateBox rating tag, or None when the file has no valid rating."""
    path = Path(path)
    try:
        if path.suffix.lower() == ".mp3":
            tags = ID3(path)
            cratebox = [frame for frame in tags.getall("POPM") if frame.email.casefold() == "cratebox"]
            frames = cratebox or tags.getall("POPM")
            if frames:
                value = max(int(frame.rating) for frame in frames)
                return 0 if value == 0 else min(5, (value * 5 + 127) // 255)
            for frame in tags.getall("TXXX"):
                if frame.desc.strip().casefold() != "rating" or not frame.text:
                    continue
                try:
                    value = float(str(frame.text[0]).strip())
                except (TypeError, ValueError):
                    continue
                if 0 <= value <= 5:
                    return round(value)
                if value <= 100:
                    return min(5, round(value / 20))
                if value <= 255:
                    return min(5, round(value * 5 / 255))
            return None

        if path.suffix.lower() == ".m4a":
            tags = MP4(path).tags or {}
            values = tags.get("----:com.apple.iTunes:RATING", [])
            for value in values:
                if isinstance(value, bytes):
                    value = value.decode("utf-8", errors="strict")
                rating = _rating_value(value)
                if rating is not None:
                    return rating
    except (OSError, MutagenError, UnicodeError, ValueError):
        return None
    return None
