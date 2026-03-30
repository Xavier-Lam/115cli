"""Login commands – authenticate and set the active user."""

from __future__ import annotations

import argparse

from cli115.cmds.auth import AuthCookieCommand, AuthValidateCommand
from cli115.cmds.base import MultiCommand
from cli115.credentials import CredType


class LoginCookieCommand(AuthCookieCommand):
    """Store cookie credentials and set as the current user."""

    def execute(self, args: argparse.Namespace) -> None:
        account = self._execute(args)
        self.cm.login(account.user_name, CredType.COOKIE)
        print(f"Authenticated as {account.user_name} (User ID: {account.user_id})")


class LoginSwitchCommand(AuthValidateCommand):
    """Switch the current user to a different stored account."""

    def execute(self, args: argparse.Namespace) -> None:
        account = self._execute(args)
        self.cm.login(args.username, args.cred_type)
        print(f"Switched to {account.user_name} (User ID: {account.user_id})")


class LoginCommand(MultiCommand):
    """Authenticate and set the active user, or switch to a stored account."""

    subcommands = [
        ("cookie", LoginCookieCommand),
        ("switch", LoginSwitchCommand),
    ]
