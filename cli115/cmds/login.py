"""Login commands – authenticate and set the active user."""

from __future__ import annotations

import argparse

from cli115.cmds.auth import AuthCookieCommand, AuthValidateCommand
from cli115.cmds.base import BaseCommand
from cli115.credentials import CredType


class LoginCommand(BaseCommand):
    """Authenticate and set the active user, or switch to a stored account."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cookie_cmd = LoginCookieCommand(*args, **kwargs)
        self._switch_cmd = LoginSwitchCommand(*args, **kwargs)

    def register(self, parser: argparse.ArgumentParser) -> None:
        subparsers = parser.add_subparsers(dest="login_action", required=True)
        cookie_parser = subparsers.add_parser(
            "cookie", help="Authenticate with cookie credentials"
        )
        self._cookie_cmd.register(cookie_parser)
        switch_parser = subparsers.add_parser(
            "switch", help="Switch to a different stored user"
        )
        self._switch_cmd.register(switch_parser)

    def execute(self, args: argparse.Namespace) -> None:
        if args.login_action == "cookie":
            self._cookie_cmd.execute(args)
        elif args.login_action == "switch":
            self._switch_cmd.execute(args)


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
