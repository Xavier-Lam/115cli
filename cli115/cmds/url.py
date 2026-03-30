"""Download info command – retrieves download URL and headers for a file."""

from __future__ import annotations

import argparse
import shlex

from cli115.cmds.base import BaseCommand
from cli115.cmds.formatter import PairFormatter, PairFormatterMixin


class Aria2cFormatter(PairFormatter):
    """Format download info as an aria2c command-line invocation."""

    def __init__(
        self,
        *,
        check_integrity,
        max_connection,
        min_split_size,
    ):
        self._check_integrity = check_integrity
        self._max_connection = max_connection
        self._min_split_size = min_split_size

    def format(self, pairs: list[tuple[str, object]]) -> str:
        d = dict(pairs)
        parts = [
            "aria2c",
            "-c",
            "--enable-rpc=false",
            f"-k{self._min_split_size}",
            f"-x{self._max_connection}",
            f"-s{self._max_connection}",
        ]
        if self._check_integrity:
            parts.append("--checksum=sha-1={sha1}".format(sha1=d["sha1"]))
        parts += [
            "-o",
            str(d["file_name"]),
            "--header",
            f"User-Agent: {d['user_agent']}",
            "--header",
            f"Referer: {d['referer']}",
            "--header",
            f"Cookie: {d['cookies']}",
            str(d["url"]),
        ]
        return " ".join(shlex.quote(p) for p in parts)


class UrlCommand(PairFormatterMixin, BaseCommand):
    """Get download URL and headers for a file."""

    def get_formatters(self):
        formatters = super().get_formatters()
        formatters["aria2c"] = Aria2cFormatter
        return formatters

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
        parser.add_argument("path", help="Path to the file")
        parser.add_argument(
            "--check-integrity",
            action="store_true",
            help="Include SHA-1 checksum in aria2c output",
        )
        parser.add_argument(
            "-k",
            "--min-split-size",
            default=None,
            help="Min split size for aria2c (overrides config, e.g. '8M')",
        )
        parser.add_argument(
            "-x",
            "--max-connections",
            type=int,
            default=None,
            help="Max connections to download the file",
        )

    def execute(self, args: argparse.Namespace) -> None:
        client = self._create_client()
        info = client.file.url(args.path, user_agent=self.cfg["general"]["user_agent"])

        pairs = [
            ("url", info.url),
            ("file_name", info.file_name),
            ("file_size", info.file_size),
            ("sha1", info.sha1),
            ("user_agent", info.user_agent),
            ("referer", info.referer),
            ("cookies", info.cookies),
        ]
        self.output(pairs, args)

    def get_formatter(self, name, args):
        if name == "aria2c":
            download = self.cfg["download"]
            return Aria2cFormatter(
                check_integrity=args.check_integrity,
                min_split_size=args.min_split_size or download["min_split_size"],
                max_connection=args.max_connections or download["max_connection"],
            )
        return super().get_formatter(name, args)
