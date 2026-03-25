"""Cloud download commands."""

from __future__ import annotations

import argparse
import sys

from cli115.cmds.base import BaseCommand
from cli115.cmds.formatter import format_size, ListFormatterMixin, PairFormatterMixin
from cli115.client.base import CloudTask


_STATUS_LABELS = {
    -1: "Failed",
    0: "Waiting",
    1: "Downloading",
    2: "Completed",
}


def _task_record(task: CloudTask) -> list[tuple[str, object]]:
    """Build a list of key-value pairs for a single task."""
    return [
        ("Hash", task.info_hash),
        ("Name", task.name),
        ("Size", format_size(task.size)),
        ("Status", _STATUS_LABELS.get(task.status.value, str(task.status.value))),
        ("Progress", f"{task.percent_done:.1f}%"),
    ]


class DownloadCommand(BaseCommand):
    """Cloud download (offline) operations."""

    def __init__(self):
        self._quota_cmd = DownloadQuotaCommand()
        self._list_cmd = DownloadListCommand()
        self._add_cmd = DownloadAddCommand()
        self._delete_cmd = DownloadDeleteCommand()

    def register(self, parser: argparse.ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="download_action", required=True)

        quota_parser = sub.add_parser("quota", help="Show cloud download quota")
        self._quota_cmd.register(quota_parser)

        list_parser = sub.add_parser("list", help="List cloud download tasks")
        self._list_cmd.register(list_parser)

        add_parser = sub.add_parser("add", help="Add URL(s) as cloud download tasks")
        self._add_cmd.register(add_parser)

        del_parser = sub.add_parser("delete", help="Delete cloud download tasks")
        self._delete_cmd.register(del_parser)

    def execute(self, args: argparse.Namespace) -> None:
        cmd_map = {
            "quota": self._quota_cmd,
            "list": self._list_cmd,
            "add": self._add_cmd,
            "delete": self._delete_cmd,
        }
        cmd_map[args.download_action].execute(args)


class DownloadQuotaCommand(PairFormatterMixin, BaseCommand):
    """Show cloud download quota."""

    def execute(self, args: argparse.Namespace) -> None:
        client = self._create_client()
        quota = client.download.quota()
        self.output(
            [("Remaining", quota.quota), ("Total", quota.total)],
            args,
        )


class DownloadListCommand(ListFormatterMixin, BaseCommand):
    """List cloud download tasks."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
        parser.add_argument(
            "--page", type=int, default=None, help="Page number (default: 1)"
        )

    def execute(self, args: argparse.Namespace) -> None:
        user_specified_page = args.page is not None
        page = args.page if args.page is not None else 1
        client = self._create_client()
        tasks, pagination = client.download.list(page)
        records = [_task_record(t) for t in tasks]
        self.output(records, args)
        if not user_specified_page and pagination.total > pagination.limit:
            print(
                f"Warning: {pagination.total} tasks total, showing first "
                f"{len(tasks)}. Use --page to paginate.",
                file=sys.stderr,
            )


class DownloadAddCommand(ListFormatterMixin, BaseCommand):
    """Add URL(s) as cloud download tasks."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
        parser.add_argument("urls", nargs="+", help="URL(s) to download")
        parser.add_argument(
            "--dest",
            default=None,
            help="Destination folder path for downloaded files",
        )

    def execute(self, args: argparse.Namespace) -> None:
        client = self._create_client()
        urls = args.urls
        dest_dir = getattr(args, "dest", None)
        if len(urls) == 1:
            task = client.download.add_url(urls[0], dest_dir=dest_dir)
            tasks = [task]
        else:
            tasks = client.download.add_urls(*urls, dest_dir=dest_dir)
        records = [_task_record(t) for t in tasks]
        self.output(records, args)


class DownloadDeleteCommand(BaseCommand):
    """Delete cloud download tasks."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "hashes", nargs="+", help="info_hash(es) of tasks to delete"
        )

    def execute(self, args: argparse.Namespace) -> None:
        client = self._create_client()
        client.download.delete(*args.hashes)
        for h in args.hashes:
            print(f"Deleted: {h}")
