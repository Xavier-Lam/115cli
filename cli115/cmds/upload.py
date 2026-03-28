"""Upload command."""

from __future__ import annotations

import argparse

from cli115.cmds.base import BaseCommand
from cli115.cmds.formatter import format_entry, PairFormatterMixin
from cli115.exceptions import AlreadyExistsError, CommandLineError
from cli115.tools import upload


class UploadCommand(PairFormatterMixin, BaseCommand):
    """Upload a local file to the remote path."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
        parser.add_argument("local_path", help="Local file path")
        parser.add_argument("remote_path", help="Remote destination path")
        parser.add_argument(
            "--instant-only",
            action="store_true",
            help=(
                "Only attempt instant (hash-based) upload. "
                "Files smaller than 2 MB are still uploaded normally."
            ),
        )

    def execute(self, args: argparse.Namespace) -> None:
        try:
            result = upload(
                self._create_client(),
                args.local_path,
                args.remote_path,
                instant_only=args.instant_only,
            )
        except AlreadyExistsError:
            raise CommandLineError(
                f"Cannot upload directory: remote path '{args.remote_path}' is a file"
            )
        self.output(format_entry(result), args)
