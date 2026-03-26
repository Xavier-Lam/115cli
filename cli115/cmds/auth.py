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
    """Save cookie credentials for the authenticated user (user_name from account)."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "cookie_value",
            nargs="?",
            help="Cookie string from browser",
        )
        parser.add_argument("--uid", help="UID cookie value")
        parser.add_argument("--cid", help="CID cookie value")
        parser.add_argument("--seid", help="SEID cookie value")
        parser.add_argument("--kid", help="KID cookie value")

    def execute(self, args: argparse.Namespace) -> None:
        # Determine cookies: prefer `cookie_value` if provided, otherwise
        # use the four individual cookie flags.
        if args.cookie_value:
            cookies = _parse_cookie_string(args.cookie_value)
        else:
            if not (args.uid and args.cid and args.seid and args.kid):
                print(
                    "Error: Provide either a cookie string or all of --uid, --cid, --seid, --kid",
                    file=sys.stderr,
                )
                sys.exit(1)
            cookies = {
                "UID": args.uid,
                "CID": args.cid,
                "SEID": args.seid,
                "KID": args.kid,
            }

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

        save_cookie_credential(account.user_name, cookies)


def _parse_cookie_string(cookie_str: str) -> dict[str, str]:
    sc = SimpleCookie()
    sc.load(cookie_str)
    return {key: morsel.value for key, morsel in sc.items()}
