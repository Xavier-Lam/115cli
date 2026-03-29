"""Upload command."""

from __future__ import annotations

import argparse

from cli115.cmds.base import BaseCommand
from cli115.cmds.formatter import format_entry, PairFormatterMixin
from cli115.exceptions import CommandLineError
from cli115.helpers import parse_size
from cli115.tools import upload


class UploadCommand(PairFormatterMixin, BaseCommand):
    """Upload a local file or directory to the remote path."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
        parser.add_argument("local_path", help="local file or directory path")
        parser.add_argument("remote_path", help="remote destination path")
        parser.add_argument(
            "--instant-only",
            type=parse_size,
            default=None,
            metavar="SIZE",
            help=(
                "Force instant (hash-based) upload for files at or above SIZE "
                "(e.g. '100MB', '1GB').  Raises an error if the server does not "
                "have a matching copy.  Values below 2 MB are ignored."
            ),
        )
        parser.add_argument(
            "--include",
            action="append",
            default=None,
            metavar="PATTERN",
            help=(
                "Glob pattern for files to include when uploading a directory "
                "(may be repeated; only matching files are uploaded)"
            ),
        )
        parser.add_argument(
            "--exclude",
            action="append",
            default=None,
            metavar="PATTERN",
            help=(
                "Glob pattern for files to exclude when uploading a directory "
                "(may be repeated; matching files are skipped)"
            ),
        )

    def execute(self, args: argparse.Namespace) -> None:
        result = upload(
            self._create_client(),
            args.local_path,
            args.remote_path,
            instant_only=args.instant_only,
            include=args.include,
            exclude=args.exclude,
        )
        self.output(format_entry(result), args)
