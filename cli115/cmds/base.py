"""Base command class for CLI commands."""

from __future__ import annotations

from abc import ABC, abstractmethod
import argparse
from configparser import ConfigParser
import sys
from typing import Sequence, TypeVar

from cli115.auth.cookie import CookieAuth
from cli115.client import Client, create_client
from cli115.credentials import CredentialManager
from cli115.exceptions import CommandLineError


T = TypeVar("T")


class BaseCommand(ABC):
    """Abstract base for all CLI commands."""

    def __init__(
        self,
        config: ConfigParser | None = None,
        credential_manager: CredentialManager | None = None,
    ) -> None:
        self.cfg = config
        self.cm = credential_manager

    def register(self, parser: argparse.ArgumentParser) -> None:
        """Register arguments on the given parser."""

    @abstractmethod
    def execute(self, args: argparse.Namespace) -> None:
        """Execute the command with parsed arguments."""

    def _create_client(
        self, uid: str | None = None, cred_type: str | None = None
    ) -> Client:
        if uid:
            cred_type, cred = self.cm.get_credential(uid, cred_type)
        else:
            cred_type, cred = self.cm.current_credential
        if cred_type == "cookie":
            auth = CookieAuth(
                uid=cred["UID"],
                cid=cred["CID"],
                seid=cred["SEID"],
                kid=cred["KID"],
            )
            return create_client(auth)
        else:
            raise CommandLineError(f"unsupported credential type: {cred_type}")


class PaginationCommand(BaseCommand, ABC):
    """Base class for commands that support --limit / --offset pagination.

    Subclasses call :meth:`apply_pagination` with a :class:`Sequence`
    to get the slice of items to display.  When no ``--offset`` is given and
    the collection has more items than ``--limit``, a warning is printed to
    *stderr*.
    """

    _default_page_size: int = 30

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help=f"Maximum number of items to show (default: {self._default_page_size})",
        )
        parser.add_argument(
            "--offset",
            type=int,
            default=None,
            help="Number of items to skip (pagination offset)",
        )

    def apply_pagination(
        self,
        collection: Sequence[T],
        args: argparse.Namespace,
    ) -> list[T]:
        """Return a sliced list from *collection* according to --limit/--offset.

        If ``--offset`` is not provided and the collection has more items than
        ``--limit``, a warning is printed to *stderr*. Pass ``user_limit`` as
        the value of ``args.limit`` *before* any command-level default is
        applied, so the warning is suppressed when the user explicitly provided
        ``--limit``.
        """
        offset = args.offset if args.offset is not None else 0
        limit = args.limit or self._default_page_size

        items = list(collection[offset : offset + limit])
        total = len(collection)

        if not args.offset and not args.limit and total > limit:
            print(
                (
                    "Warning: {total} items total, only showing up to {limit}. "
                    "Use --offset and --limit to paginate."
                ).format(total=total, limit=limit),
                file=sys.stderr,
            )
        return items
