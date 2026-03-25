"""Remove command."""

from __future__ import annotations

import argparse

from cli115.cmds.base import BaseCommand


class RmCommand(BaseCommand):
    """Remove files or directories."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("paths", nargs="+", help="Path(s) to remove")
        parser.add_argument(
            "-r", "--recursive", action="store_true", help="Remove recursively"
        )

    def execute(self, args: argparse.Namespace) -> None:
        client = self._create_client()

        if len(args.paths) == 1:
            client.file.delete(args.paths[0], recursive=args.recursive)
        else:
            client.file.batch_delete(*args.paths, recursive=args.recursive)

        for path in args.paths:
            print(f"Removed: {path}")
