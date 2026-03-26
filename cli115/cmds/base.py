"""Base command class for CLI commands."""

from __future__ import annotations

import argparse
from abc import ABC, abstractmethod

from cli115.auth.cookie import CookieAuth
from cli115.client import Client, create_client
from cli115.cmds.config import load_current_credential


class BaseCommand(ABC):
    """Abstract base for all CLI commands."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        """Register arguments on the given parser."""

    @abstractmethod
    def execute(self, args: argparse.Namespace) -> None:
        """Execute the command with parsed arguments."""

    def _create_client(self) -> Client:
        cred = load_current_credential()
        if cred["type"] == "cookie":
            cookies = cred["cookies"]
            auth = CookieAuth(
                uid=cookies["UID"],
                cid=cookies["CID"],
                seid=cookies["SEID"],
                kid=cookies["KID"],
            )
        else:
            raise ValueError(f"Unsupported credential type: {cred['type']}")
        return create_client(auth)
