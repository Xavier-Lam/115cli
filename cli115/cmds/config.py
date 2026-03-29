"""Config command – display the current configuration."""

from __future__ import annotations

import argparse
import io

from cli115.cmds.base import BaseCommand


class ConfigCommand(BaseCommand):
    """Show the current configuration as an INI file."""

    def execute(self, args: argparse.Namespace) -> None:
        buf = io.StringIO()
        self.cfg.write(buf)
        print(buf.getvalue(), end="")
