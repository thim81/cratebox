import shutil
import subprocess
from pathlib import Path

import pytest
from mutagen.id3 import POPM, TIT2
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

REPO_ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(REPO_ROOT / "cratebox"))

from core.audio_metadata import read_embedded_rating


def synthetic_mp3(path: Path) -> None:
    frame = bytes.fromhex("fffb9064") + bytes(413)
    path.write_bytes(frame * 20)
    audio = MP3(path)
    audio.add_tags()
    audio.tags.add(TIT2(encoding=3, text="Test track"))
    audio.save(v2_version=3)


def synthetic_m4a(path: Path) -> None:
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is required to generate an M4A fixture")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "0.1", "-c:a", "aac", str(path)],
        check=True,
    )


def test_read_embedded_rating_returns_none_when_unset(tmp_path):
    source = tmp_path / "track.mp3"
    synthetic_mp3(source)

    assert read_embedded_rating(source) is None


def test_read_embedded_rating_reads_mp3_popm(tmp_path):
    source = tmp_path / "track.mp3"
    synthetic_mp3(source)
    audio = MP3(source)
    audio.tags.add(POPM(email="cratebox", rating=204, count=0))
    audio.save(v2_version=3)

    assert read_embedded_rating(source) == 4


def test_read_embedded_rating_reads_m4a_freeform_rating(tmp_path):
    source = tmp_path / "track.m4a"
    synthetic_m4a(source)
    audio = MP4(source)
    audio.tags["----:com.apple.iTunes:RATING"] = [b"3"]
    audio.save()

    assert read_embedded_rating(source) == 3


def test_read_embedded_rating_ignores_malformed_values(tmp_path):
    source = tmp_path / "track.mp3"
    synthetic_mp3(source)
    audio = MP3(source)
    audio.tags.add(POPM(email="cratebox", rating=0, count=0))
    audio.save(v2_version=3)

    assert read_embedded_rating(source) == 0
