"""Safe, transactional embedding of cover art in playlist audio files."""

import hashlib
import http.client
import ipaddress
import os
from pathlib import Path
import shutil
import socket
import ssl
import stat
import struct
import tempfile
from urllib.parse import urljoin, urlsplit
import uuid
import zlib

from mutagen import MutagenError
from mutagen.id3 import APIC, ID3
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover

from .config import PLAN_DIRECTORY

MAX_IMAGE_BYTES = 8 * 1024 * 1024
BACKUP_DIRECTORY = PLAN_DIRECTORY / "audio-backups"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


class ArtworkWriteError(ValueError):
    """An artwork update was rejected or could not be completed safely."""


def _path_has_symlink(path: Path) -> bool:
    path = Path(path)
    if not path.is_absolute():
        path = Path.cwd() / path
    current = Path(path.anchor)
    for part in path.parts[1:]:
        if part == "..":
            current = current.parent
            continue
        if part == ".":
            continue
        current /= part
        if current.is_symlink():
            return True
    return False


def _validate_source(path: Path) -> os.stat_result:
    path = Path(path)
    if path.suffix.lower() not in {".mp3", ".m4a"} or _path_has_symlink(path):
        raise ArtworkWriteError("Select a regular MP3 or M4A file from the playlist")
    try:
        info = path.stat()
    except OSError:
        raise ArtworkWriteError("The selected audio file is unavailable") from None
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not info.st_mode & 0o222:
        raise ArtworkWriteError("The selected audio file is not a safe writable file")
    return info


def resolve_playlist_mp3(playlist_id: str, track_id: str) -> Path:
    """Resolve one track ID through the app-owned playlist and verified plan."""
    from . import playlists

    if playlists.PLAYLIST_DIR != playlists.DEFAULT_PLAYLIST_DIR or playlists.DEFAULT_PLAYLIST_DIR.is_symlink():
        raise ArtworkWriteError("Artwork embedding is limited to CrateBox's playlists folder")
    matches = [path for path in playlists.playlist_files() if path.stem == playlist_id]
    if len(matches) != 1 or matches[0].is_symlink():
        raise ArtworkWriteError("The selected playlist is unavailable or ambiguous")
    playlist = matches[0]
    try:
        lines = playlist.read_text(encoding="utf-8-sig").splitlines()
        _, plan = playlists.read_plan_ids(playlist, lines)
    except (OSError, UnicodeError):
        raise ArtworkWriteError("The selected playlist could not be read") from None

    resolved = []
    try:
        for line_number, plan_index, audio, entry_id, _ in playlists.playlist_entries(playlist, lines, plan):
            if entry_id != track_id:
                continue
            playlist_candidate = Path(lines[line_number].strip()).expanduser()
            if not playlist_candidate.is_absolute():
                playlist_candidate = playlist.parent / playlist_candidate
            raw_path = plan[1][plan_index] if plan and plan[1] is not None else lines[line_number].strip()
            candidate = Path(raw_path).expanduser()
            if not candidate.is_absolute():
                candidate = playlist.parent / candidate
            if _path_has_symlink(playlist_candidate) or _path_has_symlink(candidate):
                raise ArtworkWriteError("The selected audio file uses a symlinked path")
            candidate = candidate.resolve(strict=True)
            if candidate != audio:
                raise ArtworkWriteError("The selected playlist entry does not match its track plan")
            _validate_source(candidate)
            resolved.append(candidate)
    except (OSError, RuntimeError, ValueError) as exc:
        if isinstance(exc, ArtworkWriteError):
            raise
        raise ArtworkWriteError("The selected audio file could not be validated") from None
    if len(resolved) != 1:
        raise ArtworkWriteError("Select exactly one supported audio track from the playlist")
    return resolved[0]


def _image_dimensions(data: bytes, mime: str) -> tuple[int, int]:
    if mime == "image/png":
        if len(data) < 45 or not data.startswith(_PNG_SIGNATURE):
            raise ArtworkWriteError("The selected image is not a valid PNG")
        if data[12:16] != b"IHDR" or struct.unpack(">I", data[8:12])[0] != 13:
            raise ArtworkWriteError("The selected image is not a valid PNG")
        width, height = struct.unpack(">II", data[16:24])
        if data[-8:-4] != b"IEND" or struct.unpack(">I", data[-12:-8])[0] != 0:
            raise ArtworkWriteError("The selected image is incomplete")
        expected_crc = struct.unpack(">I", data[29:33])[0]
        if zlib.crc32(data[12:29]) != expected_crc:
            raise ArtworkWriteError("The selected image is corrupt")
        return width, height
    if mime == "image/jpeg":
        if len(data) < 16 or not data.startswith(b"\xff\xd8\xff") or not data.endswith(b"\xff\xd9"):
            raise ArtworkWriteError("The selected image is not a valid JPEG")
        offset = 2
        while offset + 4 <= len(data):
            if data[offset] != 0xFF:
                offset += 1
                continue
            while offset < len(data) and data[offset] == 0xFF:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker in {0xD8, 0x01, *range(0xD0, 0xD8)}:
                continue
            if offset + 2 > len(data):
                break
            segment_length = int.from_bytes(data[offset : offset + 2], "big")
            if segment_length < 2 or offset + segment_length > len(data):
                break
            if marker in _JPEG_SOF and segment_length >= 7:
                height, width = struct.unpack(">HH", data[offset + 3 : offset + 7])
                return width, height
            if marker == 0xDA:
                break
            offset += segment_length
        raise ArtworkWriteError("The selected JPEG has no valid dimensions")
    raise ArtworkWriteError("Only JPEG and PNG artwork is supported")


def _validate_image(data: bytes, mime: str) -> None:
    if not isinstance(data, bytes) or not data or len(data) > MAX_IMAGE_BYTES:
        raise ArtworkWriteError("The selected image is empty or larger than 8 MiB")
    if mime not in {"image/jpeg", "image/png"}:
        raise ArtworkWriteError("Only JPEG and PNG artwork is supported")
    width, height = _image_dimensions(data, mime)
    if not width or not height or width > 10000 or height > 10000 or width * height > 50_000_000:
        raise ArtworkWriteError("The selected image dimensions are not supported")


def _fetch_https(host: str, ip_address: str, target: str):
    class PinnedHTTPSConnection(http.client.HTTPSConnection):
        def connect(self):
            raw_socket = socket.create_connection((ip_address, self.port), self.timeout, self.source_address)
            try:
                self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
            except Exception:
                raw_socket.close()
                raise

    connection = PinnedHTTPSConnection(host, 443, timeout=8, context=ssl.create_default_context())
    try:
        connection.request(
            "GET",
            target,
            headers={"User-Agent": "CrateBox/1.0", "Accept": "image/jpeg,image/png"},
        )
        response = connection.getresponse()
        body = response.read(MAX_IMAGE_BYTES + 1)
        return response.status, {key.lower(): value for key, value in response.getheaders()}, body
    finally:
        connection.close()


def download_cover_image(url: str) -> tuple[bytes, str]:
    """Fetch a small HTTPS image with pinned public DNS; follow only CAA image redirects."""
    if not isinstance(url, str) or len(url) > 2048:
        raise ArtworkWriteError("The selected image URL is invalid")
    current_url = url
    initial_host = None
    response = None
    for redirect_count in range(3):
        try:
            parsed = urlsplit(current_url)
            host = parsed.hostname
            port = parsed.port
        except ValueError:
            raise ArtworkWriteError("The selected image URL is invalid") from None
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username
            or parsed.password
            or parsed.fragment
            or port not in (None, 443)
        ):
            raise ArtworkWriteError("Only public HTTPS image URLs are supported")
        host = host.lower()
        if initial_host is None:
            initial_host = host
        is_caa_source = initial_host == "coverartarchive.org" or initial_host.endswith(".coverartarchive.org")
        if redirect_count and (
            not is_caa_source
            or host != "archive.org" and not host.endswith(".archive.org")
        ):
            raise ArtworkWriteError("The selected image host returned an untrusted redirect")
        try:
            addresses = {
                info[4][0]
                for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            }
            if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
                raise ArtworkWriteError("The selected image host is not publicly reachable")
        except (OSError, ValueError):
            raise ArtworkWriteError("The selected image host could not be validated") from None

        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        last_error = None
        for address in sorted(addresses):
            try:
                response = _fetch_https(host, address, target)
                break
            except (OSError, ssl.SSLError, http.client.HTTPException, ValueError) as exc:
                last_error = exc
        else:
            raise ArtworkWriteError("The selected image could not be downloaded") from last_error
        status, headers, data = response
        if status == 200:
            break
        location = headers.get("location", "")
        redirect_url = urljoin(current_url, location) if location else ""
        if (
            status not in {301, 302, 303, 307, 308}
            or redirect_count >= 2
            or not is_caa_source
            or not redirect_url
        ):
            raise ArtworkWriteError("The selected image host returned an error or redirect")
        current_url = redirect_url
    else:
        raise ArtworkWriteError("The selected image host returned too many redirects")

    status, headers, data = response
    if status != 200:
        raise ArtworkWriteError("The selected image host returned an error or redirect")
    try:
        content_length = int(headers.get("content-length", "0") or 0)
    except ValueError:
        raise ArtworkWriteError("The selected image host returned an invalid response") from None
    if content_length < 0 or content_length > MAX_IMAGE_BYTES or len(data) > MAX_IMAGE_BYTES:
        raise ArtworkWriteError("The selected image is larger than 8 MiB")
    mime = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    _validate_image(data, mime)
    return data, mime


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_backup(source: Path, backup_directory: Path, expected_digest: str) -> Path:
    if PLAN_DIRECTORY.is_symlink() or _path_has_symlink(backup_directory):
        raise ArtworkWriteError("The artwork backup directory is not safe")
    backup_directory.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=backup_directory, prefix=".cratebox-backup-", delete=False) as target:
            temporary = Path(target.name)
            with source.open("rb") as original:
                shutil.copyfileobj(original, target, length=1024 * 1024)
            target.flush()
            os.fsync(target.fileno())
        if _sha256(temporary) != expected_digest or _sha256(source) != expected_digest:
            raise ArtworkWriteError("The source changed while its backup was being made")
        shutil.copystat(source, temporary)
        backup = backup_directory / f"{source.stem}-{uuid.uuid4().hex}{source.suffix.lower()}"
        os.replace(temporary, backup)
        return backup
    except Exception as exc:
        if temporary:
            temporary.unlink(missing_ok=True)
        if isinstance(exc, ArtworkWriteError):
            raise
        raise ArtworkWriteError("Could not create a verified audio backup") from None


def _fingerprint(path: Path) -> tuple[int, int, int, int, str]:
    info = path.stat()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, _sha256(path)


def _artwork_snapshot(tags: ID3 | None):
    if tags is None:
        return []
    return [
        (frame.type, frame.mime, frame.desc, frame.data)
        for frame in tags.getall("APIC")
        if frame.type != 3
    ]


def _validate_staged(staged: Path, duration: float, image_data: bytes, mime: str, version: int) -> None:
    audio = MP3(staged)
    if audio.info is None or abs(audio.info.length - duration) > 1e-6:
        raise ArtworkWriteError("The staged MP3 failed its audio integrity check")
    if audio.tags is None or audio.tags.version[1] != version:
        raise ArtworkWriteError("The staged MP3 failed its ID3 tag integrity check")
    front_covers = [frame for frame in audio.tags.getall("APIC") if frame.type == 3]
    if len(front_covers) != 1 or front_covers[0].mime != mime or front_covers[0].data != image_data:
        raise ArtworkWriteError("The staged MP3 does not contain the selected cover")


def _replace_source(staged: Path, source: Path) -> None:
    os.replace(staged, source)


def _mp4_media_data(path: Path) -> tuple[str, ...]:
    """Hash each MP4 media-data atom so tag writes cannot alter audio payloads."""
    hashes = []
    try:
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            file_size = stream.tell()
            offset = 0
            while offset < file_size:
                stream.seek(offset)
                header = stream.read(8)
                if len(header) != 8:
                    raise ArtworkWriteError("The selected M4A has an invalid container")
                atom_size = int.from_bytes(header[:4], "big")
                header_size = 8
                if atom_size == 1:
                    extended = stream.read(8)
                    if len(extended) != 8:
                        raise ArtworkWriteError("The selected M4A has an invalid container")
                    atom_size = int.from_bytes(extended, "big")
                    header_size = 16
                elif atom_size == 0:
                    atom_size = file_size - offset
                if atom_size < header_size or offset + atom_size > file_size:
                    raise ArtworkWriteError("The selected M4A has an invalid container")
                if header[4:8] == b"mdat":
                    digest = hashlib.sha256()
                    remaining = atom_size - header_size
                    while remaining:
                        block = stream.read(min(1024 * 1024, remaining))
                        if not block:
                            raise ArtworkWriteError("The selected M4A has an invalid container")
                        digest.update(block)
                        remaining -= len(block)
                    hashes.append(digest.hexdigest())
                offset += atom_size
    except OSError:
        raise ArtworkWriteError("The selected M4A could not be read") from None
    if not hashes:
        raise ArtworkWriteError("The selected M4A has no audio data")
    return tuple(hashes)


def _mp4_tags_snapshot(audio: MP4):
    return {key: value for key, value in (audio.tags or {}).items() if key != "covr"}


def _embed_m4a_cover(source: Path, info: os.stat_result, image_data: bytes, mime: str) -> Path:
    try:
        original = MP4(source)
        if original.info is None:
            raise ArtworkWriteError("The selected M4A is not readable")
        duration = original.info.length
        original_tags = _mp4_tags_snapshot(original)
        media_data = _mp4_media_data(source)
        fingerprint = _fingerprint(source)
        backup = _write_backup(source, BACKUP_DIRECTORY, fingerprint[4])
    except ArtworkWriteError:
        raise
    except (OSError, MutagenError, ValueError):
        raise ArtworkWriteError("The selected file could not be backed up as a valid M4A") from None

    temporary = None
    try:
        with tempfile.NamedTemporaryFile("wb", suffix=".m4a", prefix=".cratebox-artwork-", dir=source.parent, delete=False) as staged_file:
            temporary = Path(staged_file.name)
        shutil.copyfile(source, temporary)
        os.chmod(temporary, stat.S_IMODE(info.st_mode) | stat.S_IWUSR)
        staged = MP4(temporary)
        if staged.tags is None:
            staged.add_tags()
        cover_format = MP4Cover.FORMAT_JPEG if mime == "image/jpeg" else MP4Cover.FORMAT_PNG
        staged.tags["covr"] = [MP4Cover(image_data, imageformat=cover_format)]
        staged.save()
        verified = MP4(temporary)
        covers = (verified.tags or {}).get("covr", [])
        expected_format = cover_format
        if (
            verified.info is None
            or abs(verified.info.length - duration) > 1e-6
            or _mp4_tags_snapshot(verified) != original_tags
            or len(covers) != 1
            or bytes(covers[0]) != image_data
            or covers[0].imageformat != expected_format
            or _mp4_media_data(temporary) != media_data
        ):
            raise ArtworkWriteError("The staged M4A failed its audio or artwork integrity check")
        if _fingerprint(source) != fingerprint:
            raise ArtworkWriteError("The source M4A changed during the artwork update")
        shutil.copystat(source, temporary)
        _replace_source(temporary, source)
        temporary = None
        return backup
    except ArtworkWriteError:
        raise
    except (OSError, MutagenError, ValueError, struct.error):
        raise ArtworkWriteError("Could not update M4A artwork; the original was left unchanged") from None
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def embed_cover_art(source: Path, image_data: bytes, mime: str) -> Path:
    """Back up, stage, validate, and atomically replace an MP3 or M4A's cover."""
    source = Path(source)
    info = _validate_source(source)
    _validate_image(image_data, mime)
    if source.suffix.lower() == ".m4a":
        return _embed_m4a_cover(source, info, image_data, mime)
    try:
        original_audio = MP3(source)
        if original_audio.info is None:
            raise ArtworkWriteError("The selected file is not a readable MP3")
        duration = original_audio.info.length
        non_cover_art = _artwork_snapshot(original_audio.tags)
        version = original_audio.tags.version[1] if original_audio.tags else 3
        if version not in (3, 4):
            raise ArtworkWriteError("Only MP3 files with ID3v2.3 or ID3v2.4 tags are supported")
        fingerprint = _fingerprint(source)
        backup = _write_backup(source, BACKUP_DIRECTORY, fingerprint[4])
    except ArtworkWriteError:
        raise
    except (OSError, MutagenError, ValueError):
        raise ArtworkWriteError("The selected file could not be backed up as a valid MP3") from None

    temporary = None
    try:
        with tempfile.NamedTemporaryFile("wb", suffix=".mp3", prefix=".cratebox-artwork-", dir=source.parent, delete=False) as staged_file:
            temporary = Path(staged_file.name)
        shutil.copyfile(source, temporary)
        os.chmod(temporary, stat.S_IMODE(info.st_mode) | stat.S_IWUSR)
        staged = MP3(temporary)
        if staged.tags is None:
            staged.add_tags()
        for key, frame in list(staged.tags.items()):
            if frame.FrameID == "APIC" and frame.type == 3:
                del staged.tags[key]
        staged.tags.add(APIC(encoding=3, mime=mime, type=3, desc="Front cover", data=image_data))
        staged.save(v2_version=version)
        if _artwork_snapshot(staged.tags) != non_cover_art:
            raise ArtworkWriteError("The staged MP3 did not preserve its other artwork")
        _validate_staged(temporary, duration, image_data, mime, version)
        if _fingerprint(source) != fingerprint:
            raise ArtworkWriteError("The source MP3 changed during the artwork update")
        shutil.copystat(source, temporary)
        _replace_source(temporary, source)
        temporary = None
        return backup
    except ArtworkWriteError:
        raise
    except (OSError, MutagenError, ValueError, struct.error):
        raise ArtworkWriteError("Could not update MP3 artwork; the original was left unchanged") from None
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
