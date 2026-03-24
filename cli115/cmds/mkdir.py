"""Mkdir command."""

from __future__ import annotations

import argparse
import sys

from cli115.cmds.base import BaseCommand
from cli115.cmds.formatter import format_entry, PairFormatterMixin


class MkdirCommand(PairFormatterMixin, BaseCommand):
    """Create a directory."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
        parser.add_argument("path", help="Directory path to create")
        parser.add_argument(
            "-p",
            "--parents",
            action="store_true",
            help="Create parent directories as needed",
        )

    def execute(self, args: argparse.Namespace) -> None:
        client = self._create_client()

        try:
            directory = client.file.create_directory(args.path, parents=args.parents)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        self.output(format_entry(directory), args)
