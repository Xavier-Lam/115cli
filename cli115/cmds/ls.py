"""List command."""

from __future__ import annotations

import argparse
import sys

from cli115.client import Directory, File, SortField, SortOrder
from cli115.client.base import DEFAULT_PAGE_SIZE
from cli115.cmds.base import BaseCommand
from cli115.cmds.formatter import format_size


_SORT_CHOICES = {
    "name": SortField.FILENAME,
    "size": SortField.SIZE,
    "type": SortField.TYPE,
    "modified": SortField.MODIFIED_TIME,
    "created": SortField.CREATED_TIME,
    "opened": SortField.OPEN_TIME,
}

_BOLD = "\033[1m"
_RESET = "\033[0m"


def _bold(text: str) -> str:
    try:
        if sys.stdout.isatty():
            return f"{_BOLD}{text}{_RESET}"
    except AttributeError:
        pass
    return text


class LsCommand(BaseCommand):
    """List files and directories."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "path", nargs="?", default="/", help="Directory path (default: /)"
        )
        parser.add_argument(
            "-l", "--long", action="store_true", help="Show detailed info"
        )
        parser.add_argument(
            "--sort",
            choices=list(_SORT_CHOICES.keys()),
            default="name",
            help="Sort field (default: name)",
        )
        parser.add_argument(
            "--desc", action="store_true", help="Sort in descending order"
        )
        parser.add_argument(
            "--offset", type=int, default=None, help="Pagination offset"
        )
        parser.add_argument(
            "--limit", type=int, default=None, help="Number of entries per page"
        )

    def execute(self, args: argparse.Namespace) -> None:
        user_specified_pagination = args.offset is not None or args.limit is not None
        offset = args.offset if args.offset is not None else 0
        limit = args.limit if args.limit is not None else DEFAULT_PAGE_SIZE

        sort_field = _SORT_CHOICES[args.sort]
        sort_order = SortOrder.DESC if args.desc else SortOrder.ASC

        client = self._create_client()
        entries, pagination = client.file.list(
            args.path,
            sort=sort_field,
            sort_order=sort_order,
            limit=limit,
            offset=offset,
        )

        if args.long:
            _print_long(entries)
        else:
            _print_short(entries)

        if not user_specified_pagination and pagination.total > DEFAULT_PAGE_SIZE:
            print(
                f"Warning: {pagination.total} items total, showing first {len(entries)}. "
                "Use --offset and --limit to paginate.",
                file=sys.stderr,
            )


def _print_short(entries: list[Directory | File]) -> None:
    for entry in entries:
        if entry.is_directory:
            print(_bold(entry.name + "/"))
        else:
            print(entry.name)


def _print_long(entries: list[Directory | File]) -> None:
    rows = []
    for entry in entries:
        name = entry.name + ("/" if entry.is_directory else "")
        if isinstance(entry, File):
            ftype = entry.file_type or "-"
            size = format_size(entry.size)
        else:
            ftype = "dir"
            size = "-"
        mtime = (
            entry.modified_time.strftime("%Y-%m-%d %H:%M")
            if entry.modified_time
            else "-"
        )
        rows.append((name, ftype, size, mtime, entry.id))

    if not rows:
        return

    col_name = max(len(r[0]) for r in rows)
    col_type = max(len(r[1]) for r in rows)
    col_size = max(len(r[2]) for r in rows)
    col_mtime = 16  # "YYYY-MM-DD HH:MM"

    for name, ftype, size, mtime, entry_id in rows:
        print(
            f"{name:<{col_name}}  {ftype:<{col_type}}  {size:>{col_size}}  "
            f"{mtime:<{col_mtime}}  {entry_id}"
        )
