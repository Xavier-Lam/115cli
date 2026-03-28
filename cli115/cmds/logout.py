"""Logout command – remove stored credentials for a user."""

from __future__ import annotations

import argparse

from build.lib.cli115.exceptions import CommandError
from cli115.cmds.base import BaseCommand
from cli115.credentials import CredType


class LogoutCommand(BaseCommand):
    """Remove stored credentials for a user and optionally clear the active session."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "username",
            nargs="?",
            default=None,
            help="Username to log out (default: current user)",
        )
        parser.add_argument(
            "--type",
            dest="cred_type",
            type=CredType,
            choices=list(CredType),
            default=None,
            help="Credential type to remove (default: all stored credentials)",
        )

    def execute(self, args: argparse.Namespace) -> None:
        try:
            current_uid = self.cm.current_user
            current_cred_type, _ = self.cm.current_credential
        except FileNotFoundError:
            current_uid = None

        if not args.username and not current_uid:
            raise CommandError(
                "Error: No active user to log out. Use '115cli login' to log in."
            )

        username = args.username or current_uid
        cred_type = args.cred_type
        if not args.username and not cred_type:
            # logging out current user without specifying credential type:
            # only clear the active credential type
            cred_type = current_cred_type

        self.cm.clear_credential(username, cred_type)

        if username == current_uid and cred_type == current_cred_type:
            # log out current user only when the active credential type is being removed
            self.cm.logout()
            print(f"Logged out {current_uid}.")
        elif cred_type:
            print(f"Cleared {cred_type} credentials for {username}.")
        else:
            print(f"Cleared all credentials for {username}.")
