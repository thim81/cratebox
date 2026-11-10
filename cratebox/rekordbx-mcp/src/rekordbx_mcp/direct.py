"""Direct collection access and small, revision-checked playlist transactions."""

import hashlib
import json
from pathlib import Path

from pyrekordbox import MasterDatabase
from pyrekordbox.masterdb.database import BLOB
from pyrekordbox.masterdb.models import DjmdContent, DjmdPlaylist, DjmdSongPlaylist
from pyrekordbox.masterdb.registry import RekordboxAgentRegistry
from pyrekordbox.masterdb.aux_files import MasterPlaylistXml
from pyrekordbox.utils import deobfuscate
from rekordbox_mcp.database import RekordboxDatabase
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlcipher3 import dbapi2 as sqlite

from .backup import BackupManager, DEFAULT_BACKUP_DIRECTORY
from .snapshot import require_rekordbox_closed, reject_sidecars


class DirectMasterDatabase(MasterDatabase):
    def __init__(self, path: Path):
        require_rekordbox_closed()
        if path.is_symlink() or not path.is_file():
            raise ValueError('Select an existing database file, not a symlink.')
        reject_sidecars(path)
        def connect():
            require_rekordbox_closed()
            reject_sidecars(path)
            conn = sqlite.connect(path.as_uri() + '?mode=rw', uri=True, check_same_thread=False, timeout=2)
            try:
                conn.execute("PRAGMA key = '" + deobfuscate(BLOB) + "'")
                conn.execute('SELECT count(*) FROM sqlite_master').fetchone()
                return conn
            except BaseException:
                conn.close()
                raise
        self.engine = create_engine('sqlite://', creator=connect, module=sqlite)
        self.autocommit = False
        self.registry = RekordboxAgentRegistry(self)
        self.registry.clear_buffer()
        self._events = {}
        self._db_dir = path.parent
        self._share_dir = path.parent / 'share'
        self.playlist_xml = MasterPlaylistXml(db_dir=path.parent) if path.with_name('masterPlaylists6.xml').exists() else None
        self.session = Session(self.engine)
        event.listen(self.session, 'before_commit', lambda _session: require_rekordbox_closed())

    def query(self, *entities, **kwargs):
        query = super().query(*entities, **kwargs)
        # Library ordering helpers must not count or move tombstoned entries.
        if len(entities) == 1 and entities[0] is DjmdSongPlaylist:
            query = query.filter(DjmdSongPlaylist.rb_local_deleted == 0)
        return query

    def commit(self, *args, **kwargs):
        # Library removal commits internally. Only the transaction owner may persist.
        self.flush()

    def finish(self):
        require_rekordbox_closed()
        super().commit()

    def close(self):
        try:
            super().close()
        finally:
            self.registry.enable_tracking()
            self.engine.dispose()


class DirectDatabase(RekordboxDatabase):
    def __init__(self, source: Path):
        super().__init__()
        self.source = Path(source).absolute()
        self.database_path = self.source.parent

    async def connect(self, database_path=None):
        if database_path is not None:
            raise PermissionError('Changing the configured database path is forbidden.')
        require_rekordbox_closed()
        self.db = DirectMasterDatabase(self.source)
        self._connected = True
        self._invalidate_content_cache()


def playlist_state(db, playlist_id):
    playlist = db.get_playlist(ID=playlist_id)
    if playlist is None or playlist.rb_local_deleted:
        raise ValueError('Playlist not found.')
    entries = db.query(DjmdSongPlaylist).filter(
        DjmdSongPlaylist.PlaylistID == str(playlist.ID),
        DjmdSongPlaylist.rb_local_deleted == 0,
    ).order_by(DjmdSongPlaylist.TrackNo).all()
    visible = [row for row in entries if (track := db.get_content(ID=row.ContentID)) is not None and not track.rb_local_deleted]
    state = dict(id=str(playlist.ID), name=playlist.Name,
                 editable=playlist.Attribute == 0 and len(visible) == len(entries),
                 entries=[dict(entry_id=str(row.ID), track_id=str(row.ContentID), position=int(row.TrackNo)) for row in visible])
    state['revision'] = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
    return state


class PlaylistEditor:
    def __init__(self, source: Path, backups: Path = DEFAULT_BACKUP_DIRECTORY):
        self.backups = BackupManager(source, backups)
        self.source = self.backups.source
        self.database = None
        self.source_stamp = None

    def read(self, playlist_id):
        with self.backups.lock():
            db = DirectMasterDatabase(self.source)
            try:
                return playlist_state(db, playlist_id)
            finally:
                db.close()

    def edit(self, action, playlist_id='', expected_revision='', *, name=None,
             entry_ids=None, track_ids=None, position=None, target_entry_id=None, before=True):
        entry_ids, track_ids = entry_ids or [], track_ids or []
        if action not in {'create', 'rename', 'add', 'remove', 'swap', 'move'}:
            raise ValueError('Unknown playlist operation.')
        if action in {'create', 'rename'} and (not name or not name.strip() or len(name.strip()) > 255):
            raise ValueError('Enter a playlist name of 1–255 characters.')
        if len(entry_ids) != len(set(entry_ids)) or len(entry_ids) > 1000 or len(track_ids) > 1000:
            raise ValueError('Invalid playlist selection.')
        with self.backups.lock():
            stamp = (self.source.stat().st_ino, self.source.stat().st_mtime_ns)
            if self.source_stamp is not None and stamp != self.source_stamp:
                self.backups.last = None  # A different writer invalidates our recovery interval.
            self.backups.ensure()
            db = self.database = DirectMasterDatabase(self.source)
            committed = False
            committing = False
            try:
                db.session.connection().exec_driver_sql('BEGIN IMMEDIATE')
                if action == 'create':
                    playlist = db.create_playlist(name.strip())
                    db.flush()
                    playlist_id = str(playlist.ID)
                else:
                    state = playlist_state(db, playlist_id)
                    if state['revision'] != expected_revision:
                        raise ValueError('Playlist changed; reload it before editing.')
                    if not state['editable']:
                        raise ValueError('Folders and smart playlists cannot be edited.')
                    playlist = db.get_playlist(ID=playlist_id)
                rows = {str(row.ID): row for row in db.query(DjmdSongPlaylist).filter(
                    DjmdSongPlaylist.PlaylistID == playlist_id, DjmdSongPlaylist.rb_local_deleted == 0,
                ).order_by(DjmdSongPlaylist.TrackNo).all()}
                if any(i not in rows for i in entry_ids):
                    raise ValueError('Playlist entry not found in this playlist.')
                contents = []
                for track_id in track_ids:
                    track = db.get_content(ID=track_id)
                    if track is None or track.rb_local_deleted:
                        raise ValueError('Track is not active in the collection.')
                    contents.append(track)
                if action == 'rename':
                    db.rename_playlist(playlist, name.strip())
                elif action == 'add':
                    if not contents:
                        raise ValueError('Select tracks to add.')
                    if target_entry_id is not None:
                        if target_entry_id not in rows:
                            raise ValueError('Target entry not found.')
                        position = rows[target_entry_id].TrackNo + (0 if before else 1)
                    for track in contents:
                        db.add_to_playlist(playlist, track, track_no=position)
                        db.flush()
                        if position is not None:
                            position += 1
                elif action in {'remove', 'swap'}:
                    if not entry_ids or (action == 'swap' and (len(entry_ids) != 1 or len(contents) != 1)):
                        raise ValueError('Select entries to remove, or one entry and one replacement for a swap.')
                    swap_position = rows[entry_ids[0]].TrackNo
                    for entry_id in entry_ids:
                        db.remove_from_playlist(playlist, rows[entry_id])
                        db.flush()
                    if action == 'swap':
                        db.add_to_playlist(playlist, contents[0], track_no=swap_position)
                elif action == 'move':
                    if not entry_ids:
                        raise ValueError('Select entries to move.')
                    ordered = list(rows)
                    moved = [i for i in ordered if i in entry_ids]
                    remaining = [i for i in ordered if i not in entry_ids]
                    if target_entry_id is not None:
                        if target_entry_id not in remaining:
                            raise ValueError('Select a target outside the moved entries.')
                        index = remaining.index(target_entry_id) + (0 if before else 1)
                    else:
                        if position is None or not 1 <= position <= len(remaining) + 1:
                            raise ValueError('Position is outside the playlist.')
                        index = position - 1
                    desired = remaining[:index] + moved + remaining[index:]
                    for index, entry_id in enumerate(desired, 1):
                        db.move_song_in_playlist(playlist, rows[entry_id], index)
                        db.flush()
                db.flush()
                expected = playlist_state(db, playlist_id)
                require_rekordbox_closed()
                self.backups.blocked.write_text('Commit in progress; inspect recovery if interrupted.')
                committing = True
                db.finish()
                committed = True
                result = playlist_state(db, playlist_id)
                if result != expected:
                    raise RuntimeError('Playlist verification failed after commit.')
                self.backups.blocked.unlink()
                return result
            except BaseException as error:
                db.session.rollback()
                if committed or committing:
                    self.backups.blocked.write_text('Commit outcome requires inspection; do not retry automatically.')
                    raise RuntimeError('Playlist commit outcome is uncertain; inspect recovery before editing again.') from error
                raise
            finally:
                db.close()
                self.database = None
                self.source_stamp = (self.source.stat().st_ino, self.source.stat().st_mtime_ns)
