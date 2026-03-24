"""Move command."""

from __future__ import annotations

import argparse
import sys

from cli115.cmds.base import BaseCommand


class MvCommand(BaseCommand):
    """Move files or directories."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "paths", nargs="+", help="Source path(s) followed by destination path"
        )

    def execute(self, args: argparse.Namespace) -> None:
        if len(args.paths) < 2:
            print(
                "Error: mv requires at least a source and destination path.",
                file=sys.stderr,
            )
            sys.exit(1)

        *src_paths, dst_path = args.paths
        client = self._create_client()

        try:
            if len(src_paths) == 1:
                client.file.move(src_paths[0], dst_path)
            else:
                client.file.batch_move(*src_paths, dest_dir=dst_path)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        for src in src_paths:
            print(f"Moved: {src} -> {dst_path}")
