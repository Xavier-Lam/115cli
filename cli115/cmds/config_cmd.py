"""Config command – display the current configuration."""

from __future__ import annotations

import argparse
import io

from cli115.cmds.base import BaseCommand
from cli115.cmds.config import load_config


class ConfigCommand(BaseCommand):
    """Show the current configuration as an INI file."""

    def execute(self, args: argparse.Namespace) -> None:
        config = load_config()
        buf = io.StringIO()
        config.write(buf)
        print(buf.getvalue(), end="")
