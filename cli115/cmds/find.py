"""Find command."""

from __future__ import annotations

import argparse

from cli115.client import File, FileSystemEntry
from cli115.cmds.base import PaginationCommand
from cli115.cmds.formatter import ListFormatterMixin
from cli115.helpers import format_size


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


class FindCommand(ListFormatterMixin, PaginationCommand):
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

    def execute(self, args: argparse.Namespace) -> None:
        client = self._create_client()
        collection = client.file.find(
            args.keyword,
            path=args.path,
        )

        entries = self.apply_pagination(collection, args)

        records = [_find_record(e) for e in entries]
        self.output(records, args)
