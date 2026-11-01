"""Artwork validation, metadata extraction, and override storage."""

from base64 import b64decode
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

import mutagen
from fastapi import HTTPException

from .config import ARTWORK_FILE, PLAN_DIRECTORY

def is_http_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return parsed.scheme in ("https", "http") and bool(parsed.netloc) and not parsed.username and not parsed.password
    except ValueError:
        return False

def embedded_artwork(audio: Path):
    try:
        media = mutagen.File(audio)
    except (OSError, ValueError, mutagen.MutagenError):
        return None
    if media is None:
        return None

    tags = getattr(media, "tags", None)
    pictures = list(getattr(media, "pictures", []) or [])
    if tags is not None:
        if hasattr(tags, "getall"):
            pictures.extend(tags.getall("APIC"))
        pictures.extend(tags.get("covr", []) or [])
        for encoded in tags.get("metadata_block_picture", []) or []:
            try:
                pictures.append(mutagen.flac.Picture(b64decode(encoded)))
            except (TypeError, ValueError):
                pass

    for picture in pictures:
        data = getattr(picture, "data", None)
        if data is None and isinstance(picture, bytes):
            data = picture
        if not data:
            continue
        if data.startswith(b"\xff\xd8\xff"):
            mime = "image/jpeg"
        elif data.startswith(b"\x89PNG\r\n\x1a\n"):
            mime = "image/png"
        elif data.startswith((b"GIF87a", b"GIF89a")):
            mime = "image/gif"
        elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            mime = "image/webp"
        else:
            continue
        return data, mime
    return None

def read_artwork_overrides():
    if PLAN_DIRECTORY.is_symlink() or ARTWORK_FILE.is_symlink():
        raise HTTPException(403, "Artwork settings cannot use symlinked paths")
    try:
        value = json.loads(ARTWORK_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"playlists": {}, "tracks": {}}
    except FileNotFoundError:
        return {"playlists": {}, "tracks": {}}
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise HTTPException(500, "Could not read CrateDeck artwork settings") from None


def write_artwork_overrides(value):
    if PLAN_DIRECTORY.is_symlink() or ARTWORK_FILE.is_symlink():
        raise HTTPException(403, "Artwork settings cannot use symlinked paths")
    temporary = None
    try:
        PLAN_DIRECTORY.mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=PLAN_DIRECTORY, prefix=".cratedeck-artwork-", delete=False
        ) as file:
            temporary = Path(file.name)
            file.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(ARTWORK_FILE)
    except OSError:
        if temporary:
            temporary.unlink(missing_ok=True)
        raise HTTPException(500, "Could not save CrateDeck artwork settings") from None

