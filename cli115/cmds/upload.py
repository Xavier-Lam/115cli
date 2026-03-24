"""Upload command."""

from __future__ import annotations

import argparse
import sys

from cli115.cmds.base import BaseCommand
from cli115.cmds.formatter import format_entry, PairFormatterMixin


class UploadCommand(PairFormatterMixin, BaseCommand):
    """Upload a local file to the remote path."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
        parser.add_argument("local_path", help="Local file path")
        parser.add_argument("remote_path", help="Remote destination path")

    def execute(self, args: argparse.Namespace) -> None:
        client = self._create_client()

        try:
            result = client.file.upload(args.remote_path, args.local_path)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        self.output(format_entry(result), args)
