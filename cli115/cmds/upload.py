"""Upload command."""

from __future__ import annotations

import argparse
import os

from cli115.cmds.base import BaseCommand
from cli115.cmds.formatter import format_entry, PairFormatterMixin


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
        client = self._create_client()

        # If remote path points to an existing directory, append the
        # local filename to form the final destination path.
        remote_path = args.remote_path
        try:
            entry = client.file.stat(remote_path)
            if entry.is_directory:
                file_name = os.path.basename(args.local_path)
                remote_path = remote_path.rstrip("/") + "/" + file_name
        except Exception:
            pass

        result = client.file.upload(
            remote_path,
            args.local_path,
            instant_only=args.instant_only,
        )

        self.output(format_entry(result), args)
