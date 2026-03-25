"""Account command – shows info for the authenticated account."""

from __future__ import annotations

import argparse

from cli115.cmds.base import BaseCommand
from cli115.cmds.formatter import PairFormatterMixin


class AccountCommand(PairFormatterMixin, BaseCommand):
    """Show account info."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)

    def execute(self, args: argparse.Namespace) -> None:
        client = self._create_client()

        info = client.account.info()

        pairs = [
            ("Username", info.user_name),
            ("User ID", info.user_id),
            ("VIP", info.vip),
            ("Expire", info.expire),
        ]
        self.output(pairs, args)
