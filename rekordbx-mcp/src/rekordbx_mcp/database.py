"""Replace upstream connection discovery with an explicit read-only SQLCipher URI."""

from pathlib import Path

from pyrekordbox import MasterDatabase
from pyrekordbox.masterdb.database import BLOB
from pyrekordbox.masterdb.registry import RekordboxAgentRegistry
from pyrekordbox.utils import deobfuscate
from rekordbox_mcp.database import RekordboxDatabase
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlcipher3 import dbapi2 as sqlite

from .snapshot import verify_snapshot


def content_by_ids(database: MasterDatabase, track_ids: list[str]):
    query = database.get_content()
    content_model = query.column_descriptions[0]["entity"]
    ids = [
        int(track_id) if track_id.isascii() and track_id.isdigit() else track_id
        for track_id in track_ids
    ]
    return {
        str(content.ID): content
        for content in query.filter(content_model.ID.in_(ids)).all()
    }


def open_readonly_connection(database: Path):
    database = Path(database).resolve(strict=True)
    connection = sqlite.connect(
        database.as_uri() + "?mode=ro&immutable=1",
        uri=True,
        check_same_thread=False,
    )
    try:
        connection.execute("PRAGMA key = '" + deobfuscate(BLOB) + "'")
        connection.execute("PRAGMA query_only=ON")
        connection.execute("SELECT count(*) FROM sqlite_master").fetchone()

        def authorize(action, first, second, _db, _trigger):
            if action in (sqlite.SQLITE_ATTACH, sqlite.SQLITE_DETACH):
                return sqlite.SQLITE_DENY
            if action == sqlite.SQLITE_PRAGMA and second is not None:
                return sqlite.SQLITE_DENY
            if action == sqlite.SQLITE_FUNCTION and second == "load_extension":
                return sqlite.SQLITE_DENY
            return sqlite.SQLITE_OK

        connection.set_authorizer(authorize)
        return connection
    except Exception:
        connection.close()
        raise


class SnapshotMasterDatabase(MasterDatabase):
    def __init__(self, database: Path):
        # Reuse the pinned library's query methods without its live-path discovery,
        # process scanning, writable engine or source-adjacent XML handling.
        self.engine = create_engine(
            "sqlite://",
            creator=lambda: open_readonly_connection(database),
            module=sqlite,
            poolclass=StaticPool,
        )
        self.autocommit = False
        self.registry = RekordboxAgentRegistry(self)
        self._events = {}
        self.playlist_xml = None
        self._db_dir = database.parent
        self._share_dir = database.parent / "share"
        self.session = Session(self.engine, autoflush=False)

    def commit(self, *args, **kwargs):
        raise PermissionError("Snapshot database is read-only.")

    def close(self):
        super().close()
        self.engine.dispose()


class SnapshotDatabase(RekordboxDatabase):
    def __init__(self, snapshot: Path):
        super().__init__()
        self.snapshot = Path(snapshot).resolve(strict=True)

    async def connect(self, database_path=None):
        if database_path is not None:
            raise PermissionError("Changing the snapshot path is forbidden.")
        if self.db is not None:
            await self.disconnect()
        path = verify_snapshot(self.snapshot)
        self.db = SnapshotMasterDatabase(path)
        self.database_path = self.snapshot
        self._connected = True
        self._invalidate_content_cache()
