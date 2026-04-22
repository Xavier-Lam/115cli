"""Rename command."""

from __future__ import annotations

import argparse

from cli115.cmds.base import BaseCommand


class RenameCommand(BaseCommand):
    """Rename a file or directory."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("path", help="Path to rename")
        parser.add_argument("name", help="New name")

    def execute(self, args: argparse.Namespace) -> None:
        client = self._create_client()
        client.file.rename(args.path, args.name)
        print(f"Renamed: {args.path} -> {args.name}")
