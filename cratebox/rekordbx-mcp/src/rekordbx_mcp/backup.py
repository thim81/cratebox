"""Verified cold backups and explicit recovery; never downgrade failures to warnings."""

import fcntl
import hashlib
import json
import os
import shutil
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlcipher3 import dbapi2 as sqlite
from pyrekordbox.masterdb.database import BLOB
from pyrekordbox.utils import deobfuscate

from .snapshot import require_rekordbox_closed, reject_sidecars, sha256

DEFAULT_BACKUP_DIRECTORY = Path(__file__).resolve().parents[4] / '.cratebox' / 'rekordbox-backups'
COMPANION = 'masterPlaylists6.xml'


def encrypted_connection(path: Path):
    conn = sqlite.connect(path.as_uri() + '?mode=ro', uri=True)
    try:
        conn.execute("PRAGMA key = '" + deobfuscate(BLOB) + "'")
        conn.execute('SELECT count(*) FROM sqlite_master').fetchone()
        return conn
    except BaseException:
        conn.close()
        raise


def integrity(path: Path):
    with encrypted_connection(path) as conn:
        if conn.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise RuntimeError('Backup database integrity check failed.')


def durable_copy(source: Path, destination: Path):
    if source.is_symlink() or destination.is_symlink():
        raise ValueError('Database and backup files must not be symlinks.')
    with source.open('rb') as reader, destination.open('xb') as writer:
        shutil.copyfileobj(reader, writer)
        writer.flush()
        os.fsync(writer.fileno())


class BackupManager:
    def __init__(self, source: Path, directory: Path = DEFAULT_BACKUP_DIRECTORY):
        source = Path(source).absolute()
        if source.is_symlink():
            raise ValueError('Database must not be a symlink.')
        self.source = source.resolve(strict=True)
        directory = Path(directory).absolute()
        if directory.is_symlink():
            raise ValueError('Backup directory must not be a symlink.')
        self.directory = directory.resolve()
        if self.directory.is_relative_to(self.source.parent):
            raise ValueError('Backups must be outside the original database directory.')
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.key = hashlib.sha256(str(self.source).encode()).hexdigest()[:20]
        self.last = None
        self.last_time = None
        self.stamps = None
        self.blocked = self.directory / (self.key + '.recovery-required')

    @contextmanager
    def lock(self):
        require_rekordbox_closed()
        path = self.directory / (self.key + '.lock')
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Rekordbox database is busy; try the action again.') from None
            yield
        finally:
            os.close(fd)

    def _verify(self, point: Path, *, check_integrity=True):
        if point.is_symlink() or point.parent != self.directory:
            raise ValueError('Invalid backup location.')
        manifest_path = point / 'manifest.json'
        if manifest_path.is_symlink():
            raise ValueError('Invalid backup manifest.')
        data = json.loads(manifest_path.read_text())
        if data['source'] != str(self.source) or set(data['files']) - {'master.db', COMPANION} or 'master.db' not in data['files']:
            raise ValueError('Backup does not match the selected database.')
        for name, digest in data['files'].items():
            path = point / name
            if path.is_symlink() or sha256(path) != digest:
                raise RuntimeError('Backup verification failed.')
        if check_integrity:
            if not data['recoverable']:
                raise RuntimeError('Backup preserves damaged files and is not a verified recovery point.')
            integrity(point / 'master.db')
        return data

    def _capture(self, *, recoverable=True):
        require_rekordbox_closed()
        reject_sidecars(self.source)
        point = self.directory / uuid4().hex
        point.mkdir(mode=0o700)
        conn = encrypted_connection(self.source) if recoverable else None
        try:
            if conn:
                conn.execute('BEGIN')
                conn.execute('SELECT count(*) FROM sqlite_master').fetchone()
            files = {}
            for name, source in [('master.db', self.source), (COMPANION, self.source.with_name(COMPANION))]:
                if source.exists():
                    before = sha256(source)
                    durable_copy(source, point / name)
                    if before != sha256(source) or before != sha256(point / name):
                        raise RuntimeError('Source changed during backup.')
                    files[name] = before
            require_rekordbox_closed()
            reject_sidecars(self.source)
            data = dict(source=str(self.source), files=files, recoverable=recoverable,
                        created=datetime.now(timezone.utc).isoformat())
            with (point / 'manifest.json').open('x') as stream:
                json.dump(data, stream)
                stream.flush()
                os.fsync(stream.fileno())
            self._verify(point, check_integrity=recoverable)
            return point
        except BaseException:
            shutil.rmtree(point)
            raise
        finally:
            if conn:
                conn.close()

    def ensure(self):
        require_rekordbox_closed()
        reject_sidecars(self.source)
        if self.blocked.exists():
            raise RuntimeError('Database recovery required; inspect and restore a verified backup before editing.')
        if self.last is not None and time.monotonic() - self.last_time < 300:
            try:
                stamps = {p.name: (p.stat().st_ino, p.stat().st_size, p.stat().st_mtime_ns, p.stat().st_ctime_ns)
                          for p in self.last.iterdir() if not p.is_symlink()}
                if stamps != self.stamps:
                    raise RuntimeError('Backup changed during cooldown; editing is blocked.')
            except OSError as error:
                raise RuntimeError('Backup is unavailable; editing is blocked.') from error
            return self.last
        self.last = self._capture()
        self.last_time = time.monotonic()
        self.stamps = {p.name: (p.stat().st_ino, p.stat().st_size, p.stat().st_mtime_ns, p.stat().st_ctime_ns)
                       for p in self.last.iterdir()}
        return self.last

    def list(self):
        result = []
        for point in sorted(self.directory.iterdir()):
            if point.is_dir() and not point.is_symlink() and (point / 'manifest.json').is_file():
                data = json.loads((point / 'manifest.json').read_text())
                if data.get('source') == str(self.source):
                    result.append({'id': point.name, 'created': data['created'], 'recoverable': data['recoverable']})
        return result

    def restore(self, backup_id: str):
        if len(backup_id) != 32 or any(c not in '0123456789abcdef' for c in backup_id):
            raise ValueError('Invalid backup ID.')
        point = self.directory / backup_id
        with self.lock():
            data = self._verify(point)
            # Preserve even corrupt current bytes before replacing anything.
            preserved = self._capture(recoverable=False)
            self.blocked.write_text(f'Restore interrupted; pre-restore files: {preserved.name}')
            require_rekordbox_closed()
            reject_sidecars(self.source)
            for name in ('master.db', COMPANION):
                target = self.source if name == 'master.db' else self.source.with_name(name)
                if target.is_symlink():
                    raise ValueError('Restore destination must not be a symlink.')
                if name in data['files']:
                    staged = target.with_name('.' + target.name + '.' + uuid4().hex)
                    try:
                        durable_copy(point / name, staged)
                        os.replace(staged, target)
                    finally:
                        staged.unlink(missing_ok=True)
                else:
                    target.unlink(missing_ok=True)
            integrity(self.source)
            for name, digest in data['files'].items():
                if sha256(self.source if name == 'master.db' else self.source.with_name(name)) != digest:
                    raise RuntimeError('Restored database verification failed.')
            self.blocked.unlink()
            self.last = None
            return {'restored': backup_id, 'preserved': preserved.name}
