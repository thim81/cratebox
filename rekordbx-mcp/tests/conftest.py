import json

import pytest
from sqlalchemy import MetaData, create_engine


@pytest.fixture
def encrypted_database(tmp_path):
    from pyrekordbox.masterdb.database import BLOB
    from pyrekordbox.masterdb.models import Base, DjmdArtist, DjmdContent
    from pyrekordbox.utils import deobfuscate
    from sqlcipher3 import dbapi2

    path = tmp_path / "master.db"
    def connect():
        conn = dbapi2.connect(path)
        conn.execute("PRAGMA key = '" + deobfuscate(BLOB) + "'")
        return conn
    engine = create_engine("sqlite://", creator=connect, module=dbapi2)
    # Actual libraries permit absent metadata; the upstream ORM annotations
    # otherwise generate stricter NOT NULL constraints in a synthetic schema.
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        copied = table.to_metadata(metadata)
        for column in copied.columns:
            if not column.primary_key:
                column.nullable = True
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(DjmdArtist.__table__.insert().values(ID="2", Name="Daft Punk"))
        conn.execute(DjmdContent.__table__.insert().values(
            ID="1", Title="One More Time", ArtistID="2", BPM=12300,
            Length=320, Rating=4, DJPlayCount=5, rb_local_deleted=0,
            FolderPath="/private/original/music/track.mp3",
        ))
    engine.dispose()
    return path


@pytest.fixture
def snapshot(encrypted_database):
    from rekordbx_mcp.snapshot import sha256
    directory = encrypted_database.parent
    (directory / "manifest.json").write_text(json.dumps({
        "format": 1, "sha256": sha256(encrypted_database),
    }))
    return directory


@pytest.fixture
def playable_snapshot(encrypted_database, tmp_path):
    from pyrekordbox.masterdb.database import BLOB
    from pyrekordbox.utils import deobfuscate
    from sqlcipher3 import dbapi2
    from rekordbx_mcp.snapshot import sha256

    music = tmp_path / "music"
    music.mkdir()
    first = music / "Été #1.mp3"
    second = music / "Second track.mp3"
    first.write_bytes(b"synthetic audio one")
    second.write_bytes(b"synthetic audio two")
    connection = dbapi2.connect(encrypted_database)
    try:
        connection.execute("PRAGMA key = '" + deobfuscate(BLOB) + "'")
        connection.execute("UPDATE djmdContent SET FolderPath=? WHERE ID='1'", (str(first),))
        connection.executemany(
            "INSERT INTO djmdContent (ID, Title, FolderPath, rb_local_deleted) VALUES (?, ?, ?, ?)",
            [
                ("2", "Second", str(second), 0),
                ("3", "Missing", str(music / "missing.mp3"), 0),
                ("4", "Deleted", str(first), 1),
                ("5", "Unsafe", str(music / "bad\n#EXTINF:0,injected.mp3"), 0),
                ("6", "Relative", "relative.mp3", 0),
                ("7", "Directory", str(music), 0),
            ],
        )
        connection.commit()
    finally:
        connection.close()
    (tmp_path / "manifest.json").write_text(json.dumps({
        "format": 1, "sha256": sha256(encrypted_database),
    }))
    return tmp_path
