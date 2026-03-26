"""Authentication commands."""

from __future__ import annotations

import argparse
import sys
from http.cookies import SimpleCookie

from cli115.auth import CookieAuth
from cli115.client import create_client
from cli115.cmds.base import BaseCommand
from cli115.cmds.config import save_cookie_credential


class AuthCommand(BaseCommand):
    """Parent command for authentication subcommands."""

    def __init__(self):
        self._cookie_cmd = AuthCookieCommand()

    def register(self, parser: argparse.ArgumentParser) -> None:
        subparsers = parser.add_subparsers(dest="auth_action", required=True)
        cookie_parser = subparsers.add_parser("cookie", help="Authenticate with cookie")
        self._cookie_cmd.register(cookie_parser)

    def execute(self, args: argparse.Namespace) -> None:
        if args.auth_action == "cookie":
            self._cookie_cmd.execute(args)


class AuthCookieCommand(BaseCommand):
    """Save cookie credentials for a user."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("user", help="User identifier (UID)")
        parser.add_argument("cookie_value", help="Cookie string from browser")

    def execute(self, args: argparse.Namespace) -> None:
        cookies = _parse_cookie_string(args.cookie_value)
        required = {"UID", "CID", "SEID", "KID"}
        missing = required - set(cookies.keys())
        if missing:
            print(
                f"Error: Missing required cookies: {', '.join(sorted(missing))}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Validate the saved cookie by calling account info
        auth = CookieAuth(
            uid=cookies["UID"],
            cid=cookies["CID"],
            seid=cookies["SEID"],
            kid=cookies["KID"],
        )
        client = create_client(auth)
        account = client.account.info()
        print(f"Authenticated as {account.user_name} (User ID: {account.user_id})")

        save_cookie_credential(args.user, cookies)


def _parse_cookie_string(cookie_str: str) -> dict[str, str]:
    sc = SimpleCookie()
    sc.load(cookie_str)
    return {key: morsel.value for key, morsel in sc.items()}
