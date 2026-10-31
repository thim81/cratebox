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
