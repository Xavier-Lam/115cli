"""Info command."""

from __future__ import annotations

import argparse

from cli115.cmds.base import BaseCommand
from cli115.cmds.formatter import format_entry, PairFormatterMixin


class StatCommand(PairFormatterMixin, BaseCommand):
    """Show file or directory info."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
        parser.add_argument("path", help="Path to file or directory")

    def execute(self, args: argparse.Namespace) -> None:
        client = self._create_client()

        entry = client.file.stat(args.path)

        self.output(format_entry(entry), args)
