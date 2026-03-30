"""Cloud download commands."""

from __future__ import annotations

import argparse

from cli115.client.models import CloudTask
from cli115.cmds.base import BaseCommand, MultiCommand, PaginationCommand
from cli115.cmds.formatter import format_size, ListFormatterMixin, PairFormatterMixin


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


class DownloadQuotaCommand(PairFormatterMixin, BaseCommand):
    """Show cloud download quota."""

    def execute(self, args: argparse.Namespace) -> None:
        client = self._create_client()
        quota = client.download.quota()
        self.output(
            [("Remaining", quota.quota), ("Total", quota.total)],
            args,
        )


class DownloadListCommand(ListFormatterMixin, PaginationCommand):
    """List cloud download tasks."""

    def execute(self, args: argparse.Namespace) -> None:
        client = self._create_client()
        collection = client.download.list()

        tasks = self.apply_pagination(collection, args)
        records = [_task_record(t) for t in tasks]
        self.output(records, args)


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


class DownloadCommand(MultiCommand):
    """Cloud download (offline) operations."""

    subcommands = [
        ("quota", DownloadQuotaCommand),
        ("list", DownloadListCommand),
        ("add", DownloadAddCommand),
        ("delete", DownloadDeleteCommand),
    ]
