import argparse
import sys
from pathlib import Path

from .snapshot import create_snapshot, latest_snapshot, rekordbox_is_running

DEFAULT_SNAPSHOT_DIRECTORY = (
    Path(__file__).resolve().parents[4]
    / "rekordbx-mcp" / ".cache" / "rekordbox-snapshots"
)


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
        "--destination", type=Path, default=DEFAULT_SNAPSHOT_DIRECTORY,
    )
    commands.add_parser(
        "snapshot", parents=[copy_options], help="Copy bytes with Rekordbox closed",
    )
    commands.add_parser(
        "start", parents=[copy_options],
        help="Make a fresh copy if Rekordbox is closed; otherwise serve the newest verified copy",
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
            if args.command == "snapshot":
                snapshot = create_snapshot(args.source, args.destination)
                print(snapshot)
                return
            if rekordbox_is_running():
                snapshot = latest_snapshot(args.destination)
                print(
                    "Rekordbox is running; serving the newest verified snapshot without copying.",
                    file=sys.stderr,
                )
            else:
                snapshot = create_snapshot(args.source, args.destination)
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
