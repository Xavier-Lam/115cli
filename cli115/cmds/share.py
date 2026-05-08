"""Share link commands."""

from __future__ import annotations

import argparse

from cli115.cmds.base import BaseCommand, MultiCommand
from cli115.cmds.formatter import PairFormatterMixin
from cli115.helpers import parse_share_url


class ShareInfoCommand(PairFormatterMixin, BaseCommand):
    """Get basic metadata of a share link."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
        parser.add_argument("url", help="Share URL or share code")
        parser.add_argument(
            "-p",
            "--password",
            default=None,
            help="Share password (receive code)",
        )

    def execute(self, args: argparse.Namespace) -> None:
        share_code, parsed_password = parse_share_url(args.url)
        password = args.password or parsed_password
        client = self._create_client()
        info = client.share.info(share_code, password=password)
        self.output(
            [
                ("Share Code", info.share_code),
                ("Share ID", info.share_id),
                ("Title", info.title),
                ("Owner", info.owner_name),
                ("Owner ID", info.owner_id),
                ("Has Password", info.has_password),
                ("Password", info.receive_code),
                ("Receive Count", info.receive_count),
                ("Item Count", info.item_count),
                ("Total Size", info.total_size),
                ("Created", info.created_time),
                ("Expires", info.expire_time or "Never"),
                ("Available", info.is_available),
            ],
            args,
        )


class ShareCommand(MultiCommand):
    """Share link operations."""

    subcommands = [
        ("info", ShareInfoCommand),
    ]
