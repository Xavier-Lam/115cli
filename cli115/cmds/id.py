"""ID command."""

from __future__ import annotations

import argparse
import sys

from cli115.cmds.base import BaseCommand
from cli115.cmds.formatter import format_entry, PairFormatterMixin


class IdCommand(PairFormatterMixin, BaseCommand):
    """Show file or directory info by ID."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
        parser.add_argument("file_id", help="File or directory ID")

    def execute(self, args: argparse.Namespace) -> None:
        client = self._create_client()

        try:
            entry = client.file.id(args.file_id)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        self.output(format_entry(entry), args)
