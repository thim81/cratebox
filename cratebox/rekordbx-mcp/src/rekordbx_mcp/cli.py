"""Direct collection access and explicit backup recovery commands."""
import argparse
import json
import sys
from pathlib import Path

from .backup import BackupManager, DEFAULT_BACKUP_DIRECTORY
from .snapshot import require_rekordbox_closed


def main():
    parser = argparse.ArgumentParser(description='Direct Rekordbox access while Rekordbox and its agents are closed.')
    commands = parser.add_subparsers(dest='command', required=True)
    options = argparse.ArgumentParser(add_help=False)
    options.add_argument('--source', type=Path, default=Path.home() / 'Library/Pioneer/rekordbox/master.db')
    options.add_argument('--backup-directory', type=Path, default=DEFAULT_BACKUP_DIRECTORY)
    commands.add_parser('start', parents=[options], help='Serve the original database; Rekordbox must be closed')
    commands.add_parser('backup-list', parents=[options], help='List recovery points for this database')
    restore = commands.add_parser('restore', parents=[options], help='Restore a verified backup, preserving current files first')
    restore.add_argument('--backup-id', required=True)
    update = commands.add_parser('update-upstream', help='Update pinned upstream with compatibility checks')
    update.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'update-upstream':
            from .update import update_upstream
            print(update_upstream(Path.cwd(), check_only=args.check))
        elif args.command == 'backup-list':
            print(json.dumps(BackupManager(args.source, args.backup_directory).list(), indent=2))
        elif args.command == 'restore':
            print(json.dumps(BackupManager(args.source, args.backup_directory).restore(args.backup_id)))
        else:
            require_rekordbox_closed()
            from .launcher import serve
            raise SystemExit(serve(args.source, args.backup_directory))
    except (OSError, ValueError, RuntimeError) as error:
        print(f'rekordbx-mcp: {error}', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
