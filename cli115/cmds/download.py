"""Cloud download commands."""

from __future__ import annotations

import argparse

from cli115.client.models import CloudTask, TaskFilter, TaskStatus
from cli115.cmds.base import BaseCommand, MultiCommand, PaginationCommand
from cli115.cmds.formatter import (
    format_entry,
    format_size,
    ListFormatterMixin,
    PairFormatterMixin,
)
from cli115.exceptions import CommandLineError


_STATUS_LABELS = {
    -1: "Failed",
    0: "Waiting",
    1: "Downloading",
    2: "Completed",
}


def _task_record(task: CloudTask, completed: bool = False) -> list[tuple[str, object]]:
    """Build a list of key-value pairs for a single task."""
    rv = [
        ("Hash", task.info_hash),
        ("Name", task.name),
        ("Size", format_size(task.size)),
        ("Status", _STATUS_LABELS.get(task.status.value, str(task.status.value))),
    ]
    if completed:
        rv.append(("File ID", task.file_id))
    else:
        rv.append(("Progress", f"{task.percent_done:.1f}%"))
    return rv


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

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
        parser.add_argument(
            "--filter",
            choices=[f.value for f in TaskFilter],
            default=None,
            help="Filter tasks by status",
        )

    def execute(self, args: argparse.Namespace) -> None:
        client = self._create_client()
        filter_type = TaskFilter(args.filter) if args.filter else None
        collection = client.download.list(filter=filter_type)

        tasks = self.apply_pagination(collection, args)
        records = [
            _task_record(t, completed=(filter_type == TaskFilter.COMPLETED))
            for t in tasks
        ]
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


class DownloadClearCommand(BaseCommand):
    """Clear cloud download tasks."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--filter",
            choices=[f.value for f in TaskFilter],
            default=None,
            help="Filter tasks to clear by status (default: all)",
        )

    def execute(self, args: argparse.Namespace) -> None:
        client = self._create_client()
        filter_type = TaskFilter(args.filter) if args.filter else None
        client.download.clear(filter=filter_type)
        if args.filter:
            print(f"Cleared {args.filter} tasks")
        else:
            print("Cleared all tasks")


class DownloadStatusCommand(PairFormatterMixin, BaseCommand):
    """Show full information of a cloud download task."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
        parser.add_argument("hash", help="info_hash of the task")

    def execute(self, args: argparse.Namespace) -> None:
        client = self._create_client()
        tasks = client.download.list()
        for task in tasks:
            if task.info_hash == args.hash:
                record = _task_record(task)
                if task.status == TaskStatus.COMPLETED:
                    entry = client.file.id(task.file_id)
                    keys = set(dict(record).keys())
                    record.extend(o for o in format_entry(entry) if o[0] not in keys)
                self.output(record, args)
                break
        else:
            raise CommandLineError(f"No task found with hash: {args.hash}")


class DownloadRetryCommand(BaseCommand):
    """Retry failed cloud download tasks."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("hash", help="info_hash of the task to retry")

    def execute(self, args: argparse.Namespace) -> None:
        client = self._create_client()
        client.download.retry(args.hash)
        print(f"Retried: {args.hash}")


class DownloadCommand(MultiCommand):
    """Cloud download (offline) operations."""

    subcommands = [
        ("quota", DownloadQuotaCommand),
        ("list", DownloadListCommand),
        ("add", DownloadAddCommand),
        ("delete", DownloadDeleteCommand),
        ("clear", DownloadClearCommand),
        ("status", DownloadStatusCommand),
        ("retry", DownloadRetryCommand),
    ]
