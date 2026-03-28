"""Authentication commands – store credentials and validate them."""

from __future__ import annotations

import argparse

from cli115.auth import CookieAuth
from cli115.client import create_client
from cli115.client.models import AccountInfo
from cli115.cmds.base import BaseCommand
from cli115.credentials import CredType
from cli115.exceptions import CommandError
from cli115.helpers import parse_cookie_string


class AuthCommand(BaseCommand):
    """Store credentials for future use or validate existing ones."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cookie_cmd = AuthCookieCommand(*args, **kwargs)
        self._validate_cmd = AuthValidateCommand(*args, **kwargs)

    def register(self, parser: argparse.ArgumentParser) -> None:
        subparsers = parser.add_subparsers(dest="auth_action", required=True)
        cookie_parser = subparsers.add_parser("cookie", help="Store cookie credentials")
        self._cookie_cmd.register(cookie_parser)
        validate_parser = subparsers.add_parser(
            "validate", help="Validate stored credentials for a user"
        )
        self._validate_cmd.register(validate_parser)

    def execute(self, args: argparse.Namespace) -> None:
        if args.auth_action == "cookie":
            self._cookie_cmd.execute(args)
        elif args.auth_action == "validate":
            self._validate_cmd.execute(args)


class AuthCookieCommand(BaseCommand):
    """Store cookie credentials without changing the current user."""

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
        account = self._execute(args)
        print(
            f"Credentials stored for {account.user_name} (User ID: {account.user_id})"
        )

    def _execute(self, args: argparse.Namespace) -> AccountInfo:
        cookies = self._parse_cookies(args)
        self._validate_cookies(cookies)
        account = self._store(cookies)
        return account

    def _parse_cookies(self, args: argparse.Namespace) -> dict[str, str]:
        if args.cookie_value:
            return parse_cookie_string(args.cookie_value)
        if not (args.uid and args.cid and args.seid and args.kid):
            raise CommandError(
                "Error: Provide either a cookie string or all of --uid, --cid, --seid, --kid"
            )
        return {
            "UID": args.uid,
            "CID": args.cid,
            "SEID": args.seid,
            "KID": args.kid,
        }

    def _validate_cookies(self, cookies: dict[str, str]) -> None:
        required = {"UID", "CID", "SEID", "KID"}
        missing = required - set(cookies.keys())
        if missing:
            raise CommandError(
                f"Error: Missing required cookies: {', '.join(sorted(missing))}"
            )

    def _store(self, cookies: dict[str, str]) -> AccountInfo:
        """Validate cookies via account.info, persist them, and return account info."""
        auth = CookieAuth(
            uid=cookies["UID"],
            cid=cookies["CID"],
            seid=cookies["SEID"],
            kid=cookies["KID"],
        )
        client = create_client(auth)
        account = client.account.info()
        self.cm.save_credential(account.user_name, CredType.COOKIE, cookies)
        return account


class AuthValidateCommand(BaseCommand):
    """Validate stored credentials for a user without switching to them."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("username", help="Username whose credentials to validate")
        parser.add_argument(
            "--type",
            dest="cred_type",
            type=CredType,
            choices=list(CredType),
            default=None,
            help="Credential type to validate (default: first available type)",
        )

    def execute(self, args: argparse.Namespace) -> None:
        account = self._execute(args)
        print(f"Credentials valid for {account.user_name}")

    def _execute(self, args: argparse.Namespace) -> AccountInfo:
        client = self._create_client(args.username, args.cred_type)
        account = client.account.info()
        return account
