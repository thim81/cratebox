import argparse
import sys
from pathlib import Path

from .snapshot import create_snapshot


def main():
    parser = argparse.ArgumentParser(
        description="Read-only Rekordbox MCP using verified collection snapshots."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    copy_options = argparse.ArgumentParser(add_help=False)
    copy_options.add_argument(
        "--source", type=Path,
        default=Path.home() / "Library/Pioneer/rekordbox/master.db",
    )
    copy_options.add_argument(
        "--destination", type=Path, default=Path(".cache/rekordbox-snapshots"),
    )
    commands.add_parser(
        "snapshot", parents=[copy_options], help="Copy bytes with Rekordbox closed",
    )
    commands.add_parser(
        "start", parents=[copy_options],
        help="Check Rekordbox is closed, make a fresh copy, then start read-only MCP",
    )
    server = commands.add_parser("serve", help="Serve a verified read-only snapshot")
    server.add_argument("--snapshot", type=Path, required=True)
    update = commands.add_parser(
        "update-upstream", help="Update upstream MCP and verify compatibility",
    )
    update.add_argument("--check", action="store_true", help="Check without changing files")
    args = parser.parse_args()
    try:
        if args.command == "update-upstream":
            from .update import update_upstream
            print(update_upstream(Path.cwd(), check_only=args.check))
            return
        if args.command in ("snapshot", "start"):
            snapshot = create_snapshot(args.source, args.destination)
            if args.command == "snapshot":
                print(snapshot)
                return
            print("Fresh read-only snapshot verified; starting MCP.", file=sys.stderr)
        else:
            snapshot = args.snapshot
        from .launcher import serve
        raise SystemExit(serve(snapshot))
    except (OSError, ValueError, RuntimeError) as error:
        print(f"rekordbx-mcp: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
