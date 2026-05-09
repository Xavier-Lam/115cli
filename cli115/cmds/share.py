"""Share link commands."""

from __future__ import annotations

import argparse
from fnmatch import fnmatch

from cli115.client import File, FileSystemEntry
from cli115.cmds.base import BaseCommand, MultiCommand, PaginationCommand
from cli115.cmds.formatter import format_entry, ListFormatterMixin, PairFormatterMixin
from cli115.helpers import format_size, parse_share_url


def _share_record(entry: FileSystemEntry) -> list[tuple[str, object]]:
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


class BaseShareCommand(BaseCommand):
    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
        parser.add_argument("url", help="Share URL or share code")
        parser.add_argument(
            "-p",
            "--password",
            default=None,
            help="Share password (receive code)",
        )

    def resolve_share(self, args: argparse.Namespace) -> tuple[str, str | None]:
        share_code, parsed_password = parse_share_url(args.url)
        password = args.password or parsed_password or None
        return share_code, password


class ShareInfoCommand(PairFormatterMixin, BaseShareCommand):
    """Get basic metadata of a share link."""

    def execute(self, args: argparse.Namespace) -> None:
        share_code, password = self.resolve_share(args)
        client = self._create_client()
        info = client.share.info(share_code, password=password)
        self.output(
            [
                ("Share Code", info.share_code),
                ("Share ID", info.share_id),
                ("Title", info.title),
                ("Owner", info.owner_name),
                ("Owner ID", info.owner_id),
                ("Has Password", info.has_password),
                ("Password", info.receive_code),
                ("Receive Count", info.receive_count),
                ("Item Count", info.item_count),
                ("Total Size", info.total_size),
                ("Created", info.created_time),
                ("Expires", info.expire_time or "Never"),
                ("Available", info.is_available),
            ],
            args,
        )


class ShareListCommand(ListFormatterMixin, PaginationCommand, BaseShareCommand):
    """List entries in a shared link."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
        parser.add_argument(
            "path",
            nargs="?",
            default="/",
            help="Directory path inside the shared link (default: /)",
        )

    def execute(self, args: argparse.Namespace) -> None:
        share_code, password = self.resolve_share(args)

        client = self._create_client()
        collection = client.share.list(
            share_code,
            password=password,
            path=args.path,
        )

        entries = self.apply_pagination(collection, args)
        records = [_share_record(entry) for entry in entries]
        self.output(records, args)


class ShareStatCommand(PairFormatterMixin, BaseShareCommand):
    """Show metadata for a single shared file or directory."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
        parser.add_argument("path", help="Path to file or directory in share")

    def execute(self, args: argparse.Namespace) -> None:
        share_code, password = self.resolve_share(args)

        client = self._create_client()
        entry = client.share.stat(share_code, args.path, password=password)
        self.output(format_entry(entry), args)


class ShareSaveCommand(BaseShareCommand):
    """Save entries from a shared link to your account."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
        parser.add_argument(
            "path",
            nargs="?",
            default="/",
            help="Path in the shared link to save from (default: /)",
        )
        parser.add_argument(
            "--dest",
            default="/",
            help="Destination folder path in your account (default: /)",
        )
        parser.add_argument(
            "--include",
            action="append",
            default=None,
            metavar="PATTERN",
            help=(
                "Glob pattern for entry names to include under --path "
                "(may be repeated)"
            ),
        )
        parser.add_argument(
            "--exclude",
            action="append",
            default=None,
            metavar="PATTERN",
            help=(
                "Glob pattern for entry names to exclude under --path "
                "(may be repeated)"
            ),
        )

    def execute(self, args: argparse.Namespace) -> None:
        share_code, password = self.resolve_share(args)

        client = self._create_client()
        base_entry = client.share.stat(share_code, args.path, password=password)
        if base_entry.is_directory:
            entries = list(
                client.share.list(
                    share_code,
                    password=password,
                    path=base_entry.path or args.path,
                )
            )
        else:
            entries = [base_entry]

        selected = _filter_entries(
            entries,
            include=args.include,
            exclude=args.exclude,
        )
        if not selected:
            print("No entries matched include/exclude patterns")
            return

        client.share.save(
            share_code,
            [entry.id for entry in selected],
            password=password,
            dest_dir=args.dest,
        )
        print(f"Saved {len(selected)} item(s) to {args.dest}")


class ShareCommand(MultiCommand):
    """Share link operations."""

    subcommands = [
        ("info", ShareInfoCommand),
        ("list", ShareListCommand),
        ("stat", ShareStatCommand),
        ("save", ShareSaveCommand),
    ]


def _filter_entries(
    entries: list[FileSystemEntry],
    *,
    include: list[str] | None,
    exclude: list[str] | None,
) -> list[FileSystemEntry]:
    filtered: list[FileSystemEntry] = []
    for entry in entries:
        name = entry.name
        if include and not any(fnmatch(name, pattern) for pattern in include):
            continue
        if exclude and any(fnmatch(name, pattern) for pattern in exclude):
            continue
        filtered.append(entry)
    return filtered
