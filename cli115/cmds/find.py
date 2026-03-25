"""Find command."""

from __future__ import annotations

import argparse
import sys

from cli115.cmds.base import BaseCommand
from cli115.cmds.formatter import ListFormatterMixin, format_size
from cli115.client.base import DEFAULT_PAGE_SIZE, File, FileSystemEntry


def _find_record(entry: FileSystemEntry) -> list[tuple[str, object]]:
    """Build a compact record for a search result entry."""
    if isinstance(entry, File):
        size: object = format_size(entry.size)
        ftype: object = entry.file_type or "-"
    else:
        size = "-"
        ftype = "dir"
    mtime = (
        entry.modified_time.strftime("%Y-%m-%d %H:%M") if entry.modified_time else "-"
    )
    return [
        ("Name", entry.name + ("/" if entry.is_directory else "")),
        ("Type", ftype),
        ("Size", size),
        ("Modified", mtime),
        ("ID", entry.id),
    ]


class FindCommand(ListFormatterMixin, BaseCommand):
    """Search for files and directories."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
        parser.add_argument(
            "path",
            nargs="?",
            default=None,
            help="Directory to search within (default: global search)",
        )
        parser.add_argument("keyword", help="Search keyword")
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

        client = self._create_client()
        entries, pagination = client.file.find(
            args.keyword,
            path=args.path,
            limit=limit,
            offset=offset,
        )

        records = [_find_record(e) for e in entries]
        self.output(records, args)

        if not user_specified_pagination and pagination.total > DEFAULT_PAGE_SIZE:
            print(
                f"Warning: {pagination.total} items total, showing first "
                f"{len(entries)}. Use --offset and --limit to paginate.",
                file=sys.stderr,
            )
