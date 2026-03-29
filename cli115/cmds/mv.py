"""Move command."""

from __future__ import annotations

import argparse

from cli115.cmds.base import BaseCommand
from cli115.exceptions import CommandLineError


class MvCommand(BaseCommand):
    """Move files or directories."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "paths", nargs="+", help="Source path(s) followed by destination path"
        )

    def execute(self, args: argparse.Namespace) -> None:
        if len(args.paths) < 2:
            raise CommandLineError("mv requires at least a source and destination path")

        *src_paths, dst_path = args.paths
        client = self._create_client()

        if len(src_paths) == 1:
            client.file.move(src_paths[0], dst_path)
        else:
            client.file.batch_move(*src_paths, dest_dir=dst_path)

        for src in src_paths:
            print(f"Moved: {src} -> {dst_path}")
