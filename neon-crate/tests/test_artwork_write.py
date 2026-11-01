import json
import struct
import sys
import zlib
from pathlib import Path

import pytest
from mutagen.id3 import APIC, TIT2
from mutagen.mp3 import MP3


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "neon-crate"))
from api import artwork_write, playlists


def png(color: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00" + color))
        + chunk(b"IEND", b"")
    )


def synthetic_mp3(path: Path) -> None:
    frame = bytes.fromhex("fffb9064") + bytes(413)
    path.write_bytes(frame * 20)
    audio = MP3(path)
    audio.add_tags()
    audio.tags.add(TIT2(encoding=3, text="Test track"))
    audio.tags.add(APIC(encoding=3, mime="image/png", type=3, desc="Front", data=png(b"\xff\x00\x00")))
    audio.tags.add(APIC(encoding=3, mime="image/png", type=4, desc="Back", data=png(b"\x00\x00\xff")))
    audio.save(v2_version=3)


def mpeg_stream(path: Path) -> bytes:
    data = path.read_bytes()
    if data.startswith(b"ID3"):
        tag_size = sum((data[index] & 0x7F) << (7 * (3 - offset)) for offset, index in enumerate(range(6, 10)))
        return data[10 + tag_size :]
    return data


def playlist_fixture(tmp_path, monkeypatch, audio: Path, *, entry="42"):
    playlists_dir = tmp_path / "playlists"
    output_dir = tmp_path / "output"
    playlists_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    playlist = playlists_dir / "Set.m3u8"
    playlist.write_text(f"#EXTM3U\n{audio}\n", encoding="utf-8")
    (output_dir / "Set.json").write_text(
        json.dumps({"format": 1, "name": "Set", "tracks": [{"track_id": entry, "file_path": str(audio)}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(playlists, "PLAYLIST_DIR", playlists_dir)
    monkeypatch.setattr(playlists, "DEFAULT_PLAYLIST_DIR", playlists_dir)
    monkeypatch.setattr(playlists, "PLAN_DIRECTORY", output_dir)
    return output_dir, playlist


def test_embed_cover_backups_exact_bytes_and_preserves_mp3_tags(tmp_path, monkeypatch):
    source = tmp_path / "track.mp3"
    synthetic_mp3(source)
    original = source.read_bytes()
    original_stream = mpeg_stream(source)
    original_duration = MP3(source).info.length
    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(artwork_write, "BACKUP_DIRECTORY", backup_dir)

    backup = artwork_write.embed_cover_art(source, png(b"\x00\xff\x00"), "image/png")

    updated = MP3(source)
    assert backup.read_bytes() == original
    assert updated.info.length == pytest.approx(original_duration)
    assert mpeg_stream(source) == original_stream
    assert updated.tags.version == (2, 3, 0)
    assert str(updated.tags["TIT2"]) == "Test track"
    pictures = updated.tags.getall("APIC")
    assert [(frame.type, frame.desc) for frame in pictures] == [(4, "Back"), (3, "Front cover")]
    assert next(frame.data for frame in pictures if frame.type == 3) == png(b"\x00\xff\x00")


def test_resolve_playlist_mp3_uses_server_side_playlist_identity(tmp_path, monkeypatch):
    source = tmp_path / "music" / "track.mp3"
    source.parent.mkdir()
    synthetic_mp3(source)
    playlist_fixture(tmp_path, monkeypatch, source)

    assert artwork_write.resolve_playlist_mp3("Set", "42-1") == source
    with pytest.raises(artwork_write.ArtworkWriteError):
        artwork_write.resolve_playlist_mp3("Set", str(source))


def test_resolve_playlist_mp3_rejects_symlink_and_hardlink(tmp_path, monkeypatch):
    target = tmp_path / "music" / "track.mp3"
    target.parent.mkdir()
    synthetic_mp3(target)
    link = tmp_path / "music" / "linked.mp3"
    link.symlink_to(target)
    output, playlist = playlist_fixture(tmp_path, monkeypatch, link)
    (output / "Set.json").write_text(
        json.dumps({"format": 1, "name": "Set", "tracks": [{"track_id": "42", "file_path": str(target)}]}),
        encoding="utf-8",
    )
    with pytest.raises(artwork_write.ArtworkWriteError):
        artwork_write.resolve_playlist_mp3("Set", "42-1")

    hardlink = tmp_path / "music" / "hardlink.mp3"
    hardlink.hardlink_to(target)
    playlist.write_text(f"#EXTM3U\n{hardlink}\n", encoding="utf-8")
    (output / "Set.json").write_text(
        json.dumps({"format": 1, "name": "Set", "tracks": [{"track_id": "42", "file_path": str(hardlink)}]}),
        encoding="utf-8",
    )
    with pytest.raises(artwork_write.ArtworkWriteError):
        artwork_write.resolve_playlist_mp3("Set", "42-1")


def test_invalid_image_leaves_mp3_unchanged(tmp_path, monkeypatch):
    source = tmp_path / "track.mp3"
    synthetic_mp3(source)
    original = source.read_bytes()
    monkeypatch.setattr(artwork_write, "BACKUP_DIRECTORY", tmp_path / "backups")

    with pytest.raises(artwork_write.ArtworkWriteError):
        artwork_write.embed_cover_art(source, b"not an image", "image/png")

    assert source.read_bytes() == original
    assert not (tmp_path / "backups").exists()


def test_non_mp3_target_is_rejected_without_modification(tmp_path):
    source = tmp_path / "track.wav"
    source.write_bytes(b"RIFF not an mp3")
    original = source.read_bytes()

    with pytest.raises(artwork_write.ArtworkWriteError):
        artwork_write.embed_cover_art(source, png(b"\x01\x02\x03"), "image/png")

    assert source.read_bytes() == original


def test_download_cover_art_rejects_non_https_and_private_dns(monkeypatch):
    with pytest.raises(artwork_write.ArtworkWriteError):
        artwork_write.download_cover_image("http://images.example/cover.png")

    monkeypatch.setattr(artwork_write.socket, "getaddrinfo", lambda *_args, **_kwargs: [
        (artwork_write.socket.AF_INET, artwork_write.socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
    ])
    with pytest.raises(artwork_write.ArtworkWriteError):
        artwork_write.download_cover_image("https://images.example/cover.png")


def test_download_cover_art_pins_public_address_and_returns_validated_png(monkeypatch):
    address = (artwork_write.socket.AF_INET, artwork_write.socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
    monkeypatch.setattr(artwork_write.socket, "getaddrinfo", lambda *_args, **_kwargs: [address])
    requested = []

    def fetch(host, ip, target):
        requested.append((host, ip, target))
        return 200, {"content-type": "image/png"}, png(b"\x01\x02\x03")

    monkeypatch.setattr(artwork_write, "_fetch_https", fetch)

    data, mime = artwork_write.download_cover_image("https://images.example/covers/one.png?size=large")

    assert (data, mime) == (png(b"\x01\x02\x03"), "image/png")
    assert requested == [("images.example", "93.184.216.34", "/covers/one.png?size=large")]


def test_download_cover_art_follows_validated_cover_art_archive_redirect(monkeypatch):
    monkeypatch.setattr(
        artwork_write.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (artwork_write.socket.AF_INET, artwork_write.socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        ],
    )
    requested = []

    def fetch(host, _ip, target):
        requested.append((host, target))
        if host == "coverartarchive.org":
            return 307, {"location": "https://ia800.archive.org/download/cover/front.jpg"}, b""
        return 200, {"content-type": "image/png"}, png(b"\x01\x02\x03")

    monkeypatch.setattr(artwork_write, "_fetch_https", fetch)

    data, mime = artwork_write.download_cover_image(
        "https://coverartarchive.org/release/12345678-1234-4234-8234-123456789abc/front"
    )

    assert (data, mime) == (png(b"\x01\x02\x03"), "image/png")
    assert requested == [
        ("coverartarchive.org", "/release/12345678-1234-4234-8234-123456789abc/front"),
        ("ia800.archive.org", "/download/cover/front.jpg"),
    ]


@pytest.mark.parametrize(
    ("status", "content_type", "body"),
    [
        (302, "image/png", png(b"\x01\x02\x03")),
        (200, "text/html", png(b"\x01\x02\x03")),
        (200, "image/png", b"not png"),
        (200, "image/png", b"\x89PNG\r\n\x1a\n" + bytes(artwork_write.MAX_IMAGE_BYTES)),
    ],
)
def test_download_cover_art_rejects_redirects_bad_images_and_oversize(
    monkeypatch, status, content_type, body
):
    monkeypatch.setattr(artwork_write.socket, "getaddrinfo", lambda *_args, **_kwargs: [
        (artwork_write.socket.AF_INET, artwork_write.socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
    ])
    monkeypatch.setattr(
        artwork_write,
        "_fetch_https",
        lambda *_args: (status, {"content-type": content_type}, body),
    )

    with pytest.raises(artwork_write.ArtworkWriteError):
        artwork_write.download_cover_image("https://images.example/cover.png")


def test_backup_failure_does_not_change_source(tmp_path, monkeypatch):
    source = tmp_path / "track.mp3"
    synthetic_mp3(source)
    original = source.read_bytes()
    monkeypatch.setattr(artwork_write, "BACKUP_DIRECTORY", tmp_path / "backups")

    def fail_backup(*_args, **_kwargs):
        raise OSError("backup failed")

    monkeypatch.setattr(artwork_write, "_write_backup", fail_backup)
    with pytest.raises(artwork_write.ArtworkWriteError):
        artwork_write.embed_cover_art(source, png(b"\x01\x02\x03"), "image/png")

    assert source.read_bytes() == original


def test_tag_write_failure_does_not_change_source(tmp_path, monkeypatch):
    source = tmp_path / "track.mp3"
    synthetic_mp3(source)
    original = source.read_bytes()
    monkeypatch.setattr(artwork_write, "BACKUP_DIRECTORY", tmp_path / "backups")
    monkeypatch.setattr(artwork_write, "_write_backup", lambda *_args: tmp_path / "backup.mp3")

    def fail_save(*_args, **_kwargs):
        raise OSError("tag write failed")

    monkeypatch.setattr(artwork_write.ID3, "save", fail_save)
    with pytest.raises(artwork_write.ArtworkWriteError):
        artwork_write.embed_cover_art(source, png(b"\x01\x02\x03"), "image/png")

    assert source.read_bytes() == original


def test_replace_failure_does_not_change_source(tmp_path, monkeypatch):
    source = tmp_path / "track.mp3"
    synthetic_mp3(source)
    original = source.read_bytes()
    monkeypatch.setattr(artwork_write, "BACKUP_DIRECTORY", tmp_path / "backups")
    monkeypatch.setattr(artwork_write, "_replace_source", lambda *_args: (_ for _ in ()).throw(OSError("replace failed")))

    with pytest.raises(artwork_write.ArtworkWriteError):
        artwork_write.embed_cover_art(source, png(b"\x01\x02\x03"), "image/png")

    assert source.read_bytes() == original


def test_staged_validation_failure_does_not_change_source(tmp_path, monkeypatch):
    source = tmp_path / "track.mp3"
    synthetic_mp3(source)
    original = source.read_bytes()
    monkeypatch.setattr(artwork_write, "BACKUP_DIRECTORY", tmp_path / "backups")

    def fail_validation(*_args, **_kwargs):
        raise artwork_write.ArtworkWriteError("staged MP3 validation failed")

    monkeypatch.setattr(artwork_write, "_validate_staged", fail_validation)
    with pytest.raises(artwork_write.ArtworkWriteError):
        artwork_write.embed_cover_art(source, png(b"\x01\x02\x03"), "image/png")

    assert source.read_bytes() == original


def test_concurrent_source_change_is_not_overwritten(tmp_path, monkeypatch):
    source = tmp_path / "track.mp3"
    synthetic_mp3(source)
    original = source.read_bytes()
    changed = original + b"changed concurrently"
    monkeypatch.setattr(artwork_write, "BACKUP_DIRECTORY", tmp_path / "backups")
    real_validate = getattr(artwork_write, "_validate_staged", lambda *_args: None)

    def change_source(*args, **kwargs):
        real_validate(*args, **kwargs)
        source.write_bytes(changed)

    monkeypatch.setattr(artwork_write, "_validate_staged", change_source)
    with pytest.raises(artwork_write.ArtworkWriteError):
        artwork_write.embed_cover_art(source, png(b"\x01\x02\x03"), "image/png")

    assert source.read_bytes() == changed


def test_embed_endpoint_writes_only_selected_mp3_and_clears_old_override(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from api.app import app as api_app
    from api import artwork_data

    source = tmp_path / "music" / "track.mp3"
    source.parent.mkdir()
    synthetic_mp3(source)
    original = source.read_bytes()
    output, _ = playlist_fixture(tmp_path, monkeypatch, source)
    monkeypatch.setattr(artwork_data, "PLAN_DIRECTORY", output)
    monkeypatch.setattr(artwork_data, "ARTWORK_FILE", output / "cratedeck-artwork.json")
    monkeypatch.setattr(artwork_write, "BACKUP_DIRECTORY", output / "audio-backups")
    (output / "cratedeck-artwork.json").write_text(
        json.dumps({"playlists": {}, "tracks": {"Set": {"42-1": "https://old.example/cover.png"}}}),
        encoding="utf-8",
    )
    selected = png(b"\x00\xff\x00")
    monkeypatch.setattr(artwork_write, "download_cover_image", lambda _url: (selected, "image/png"))

    with TestClient(api_app) as client:
        response = client.put(
            "/api/artwork/embed",
            json={"playlist_id": "Set", "track_id": "42-1", "image_url": "https://images.example/cover.png"},
            headers={"Origin": "http://localhost:8080"},
        )

    assert response.status_code == 200, response.text
    assert "track.mp3" not in response.text
    assert "file_path" not in response.json()
    assert response.json()["artwork_url"].startswith("/api/playlists/Set/tracks/42-1/artwork?v=")
    assert source.read_bytes() != original
    assert next(frame.data for frame in MP3(source).tags.getall("APIC") if frame.type == 3) == selected
    assert artwork_data.read_artwork_overrides()["tracks"] == {}
    assert len(list((output / "audio-backups").glob("*.mp3"))) == 1


def test_embed_endpoint_returns_a_fresh_artwork_url_for_each_update(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from api.app import app as api_app

    source = tmp_path / "music" / "track.mp3"
    source.parent.mkdir()
    synthetic_mp3(source)
    playlist_fixture(tmp_path, monkeypatch, source)
    monkeypatch.setattr(artwork_write, "BACKUP_DIRECTORY", tmp_path / "backups")
    selected_images = [png(b"\x00\xff\x00"), png(b"\x00\x00\xff")]
    monkeypatch.setattr(
        artwork_write,
        "download_cover_image",
        lambda _url: (selected_images.pop(0), "image/png"),
    )
    request = {
        "playlist_id": "Set",
        "track_id": "42-1",
        "image_url": "https://images.example/cover.png",
    }

    with TestClient(api_app) as client:
        first = client.put("/api/artwork/embed", json=request, headers={"Origin": "http://localhost:8080"})
        second = client.put("/api/artwork/embed", json=request, headers={"Origin": "http://localhost:8080"})

    assert first.status_code == second.status_code == 200
    assert first.json()["artwork_url"] != second.json()["artwork_url"]


def test_embed_endpoint_rejects_untrusted_origin_without_downloading_or_writing(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from api.app import app as api_app

    source = tmp_path / "music" / "track.mp3"
    source.parent.mkdir()
    synthetic_mp3(source)
    original = source.read_bytes()
    playlist_fixture(tmp_path, monkeypatch, source)
    called = []
    monkeypatch.setattr(artwork_write, "download_cover_image", lambda _url: called.append(True))

    with TestClient(api_app) as client:
        response = client.put(
            "/api/artwork/embed",
            json={"playlist_id": "Set", "track_id": "42-1", "image_url": "https://images.example/cover.png"},
            headers={"Origin": "https://attacker.example"},
        )

    assert response.status_code == 403
    assert not called
    assert source.read_bytes() == original


def test_embed_endpoint_restores_old_override_when_mp3_write_fails(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from api.app import app as api_app
    from api import artwork_data

    source = tmp_path / "music" / "track.mp3"
    source.parent.mkdir()
    synthetic_mp3(source)
    original = source.read_bytes()
    output, _ = playlist_fixture(tmp_path, monkeypatch, source)
    monkeypatch.setattr(artwork_data, "PLAN_DIRECTORY", output)
    monkeypatch.setattr(artwork_data, "ARTWORK_FILE", output / "cratedeck-artwork.json")
    old_override = "https://old.example/cover.png"
    (output / "cratedeck-artwork.json").write_text(
        json.dumps({"playlists": {}, "tracks": {"Set": {"42-1": old_override}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(artwork_write, "download_cover_image", lambda _url: (png(b"\x01\x02\x03"), "image/png"))

    def fail_write(*_args, **_kwargs):
        raise artwork_write.ArtworkWriteError("staged write failed")

    monkeypatch.setattr(artwork_write, "embed_cover_art", fail_write)
    with TestClient(api_app) as client:
        response = client.put(
            "/api/artwork/embed",
            json={"playlist_id": "Set", "track_id": "42-1", "image_url": "https://images.example/cover.png"},
            headers={"Origin": "http://localhost:8080"},
        )

    assert response.status_code == 400
    assert source.read_bytes() == original
    assert artwork_data.read_artwork_overrides()["tracks"]["Set"]["42-1"] == old_override
