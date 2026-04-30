"""df command – shows disk space usage."""

from __future__ import annotations

import argparse

from cli115.cmds.base import BaseCommand
from cli115.cmds.formatter import PairFormatterMixin
from cli115.helpers import format_size


class DfCommand(PairFormatterMixin, BaseCommand):
    """Show disk space usage."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)

    def execute(self, args: argparse.Namespace) -> None:
        client = self._create_client()
        info = client.account.usage()
        self.output(
            [
                ("Total", format_size(info.total)),
                ("Used", format_size(info.used)),
                ("Free", format_size(info.remaining)),
            ],
            args,
        )
