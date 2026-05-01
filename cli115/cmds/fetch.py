"""Fetch command."""

from __future__ import annotations

import argparse
import os
import time

from tqdm import tqdm

from cli115.client import Client
from cli115.client.models import Progress
from cli115.cmds.base import BaseCommand, WorkerCommand
from cli115.exceptions import CommandLineError
from cli115.fetcher import DEFAULT_CHUNK_SIZE, FetchEntry, Fetcher
from cli115.helpers import format_size, parse_size


class FetchCommand(WorkerCommand, BaseCommand):
    """Download a remote file or folder to local disk."""

    client: Client | None = None
    fetcher: Fetcher | None = None

    def register(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("path", nargs="?", help="Remote file or folder path on 115")
        parser.add_argument(
            "--id",
            dest="file_id",
            default=None,
            help="Fetch by remote file/folder ID instead of path",
        )
        parser.add_argument(
            "--chunk-size",
            type=parse_size,
            default=format_size(DEFAULT_CHUNK_SIZE),
            help=(
                "Chunk size for downloading "
                f"(default: {format_size(DEFAULT_CHUNK_SIZE)}, e.g. '4MB', '1048576')"
            ),
        )
        parser.add_argument(
            "--check-integrity",
            action="store_true",
            help="Validate file integrity after download",
        )
        parser.add_argument(
            "-o",
            "--output",
            default=None,
            help="Local output path (default: current dir with remote name)",
        )
        parser.add_argument(
            "--plan",
            action="store_true",
            default=False,
            help="Show planned files before downloading",
        )
        parser.add_argument(
            "--include",
            action="append",
            default=None,
            metavar="PATTERN",
            help=(
                "Glob pattern for files to include when downloading a directory "
                "(may be repeated; only matching files are downloaded)"
            ),
        )
        parser.add_argument(
            "--exclude",
            action="append",
            default=None,
            metavar="PATTERN",
            help=(
                "Glob pattern for files to exclude when downloading a directory "
                "(may be repeated; matching files are skipped)"
            ),
        )
        parser.add_argument(
            "-T",
            "--no-target-directory",
            action="store_true",
            default=False,
            help=(
                "Treat output as the exact destination rather than a directory "
                "to download into (never append the remote folder name)"
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Only show files that would be downloaded without downloading",
        )
        parser.add_argument(
            "-s",
            "--silent",
            action="store_true",
            default=False,
            help="Do not report progress, only print the final result",
        )

    def execute(self, args: argparse.Namespace) -> None:
        if not args.file_id and not args.path:
            raise CommandLineError("either 'path' or '--id' is required")
        if args.file_id and args.path:
            raise CommandLineError("use either 'path' or '--id', not both")

        self.client = self._create_client()
        self.fetcher = Fetcher(
            self.client,
            dry_run=args.dry_run,
            user_agent=self.cfg["general"]["user_agent"],
            chunk_size=args.chunk_size,
        )

        with FetchProgress(
            self.fetcher,
            show_plan=args.plan or args.dry_run,
            show_progress=not args.silent and not args.dry_run,
        ):
            result = self.run_worker(args)

        failed_entries = [
            entry for entry in self.fetcher.entries if entry.error is not None
        ]
        if failed_entries:
            self.warn("{0} file(s) failed to fetch".format(len(failed_entries)))
        for entry in failed_entries:
            self.warn(
                "- {0} -> {1}: {2}".format(
                    entry.remote_entry.path,
                    os.fspath(entry.local_path),
                    entry.error,
                )
            )

        if result:
            print(f"Saved to {result}")

    def worker(self, args: argparse.Namespace):
        info = (
            self.client.file.id(args.file_id)
            if args.file_id
            else self.client.file.stat(args.path)
        )

        output = args.output
        if not output:
            output = info.name
        elif os.path.isdir(output):
            output = os.path.join(output, info.name)

        check_integrity = args.check_integrity or self.cfg.getboolean(
            "download", "check_integrity", fallback=False
        )

        return self.fetcher.fetch(
            info,
            output,
            check_integrity=check_integrity,
            include=args.include,
            exclude=args.exclude,
            no_target_dir=args.no_target_directory,
        )


class FetchProgress:
    def __init__(
        self,
        fetcher: Fetcher,
        *,
        show_plan: bool = False,
        show_progress: bool = True,
    ):
        self.fetcher = fetcher
        self.show_plan = show_plan
        self.show_progress = show_progress

        self.current_text: tqdm | None = None
        self.current_bar: tqdm | None = None
        self.overall_text: tqdm | None = None
        self.overall_bar: tqdm | None = None

        self.started_at: float | None = None
        self.ended_at: float | None = None
        self.total_files = 0
        self.total_size = 0
        self.completed_files = 0
        self.completed_bytes = 0

        self._current_entry: FetchEntry | None = None

    @property
    def current_entry(self) -> FetchEntry | None:
        return self._current_entry

    @current_entry.setter
    def current_entry(self, entry: FetchEntry) -> None:
        if not (self._current_entry is entry):
            self._current_entry = entry
            if self.current_bar is not None:
                self.current_bar.reset(max(entry.remote_entry.size, 1))
            if self.overall_text is not None:
                self.overall_text.set_description_str(
                    "{0} ({1}/{2})".format(
                        entry.remote_entry.path,
                        self.completed_files,
                        self.total_files,
                    ),
                    refresh=True,
                )

    def init(self):
        self.fetcher.on_entry_added.connect(self.on_added)
        self.started_at = time.monotonic()

    def close(self):
        self.ended_at = time.monotonic()
        if self.overall_bar:
            self.current_text.close()
            self.current_bar.close()
            self.overall_text.close()
            self.overall_bar.close()
            print()

    def report(self):
        if self.started_at is None or self.ended_at is None:
            return

        elapsed = self.ended_at - self.started_at
        tqdm.write(
            "Fetch finished in {0:.1f}s: {1} total, {2} files downloaded".format(
                elapsed,
                format_size(self.total_size),
                self.completed_files,
            )
        )

    def on_added(self, sender, **kw):
        entries: list[FetchEntry] = kw["entries"]
        if self.show_plan:
            start = len(self.fetcher.entries) - len(entries) + 1
            for idx, entry in enumerate(entries, start=start):
                print(
                    "{0}. {1} -> {2} ({3})".format(
                        idx,
                        entry.remote_entry.path,
                        os.fspath(entry.local_path),
                        format_size(entry.remote_entry.size),
                    )
                )

        if not self.show_progress or not entries:
            return

        self.total_files = len(self.fetcher.entries)
        self.total_size = max(sum(e.remote_entry.size for e in self.fetcher.entries), 1)
        if self.overall_bar is None:
            self.create_progress_bars()
        else:
            self.overall_bar.total = self.total_size
            self.overall_bar.refresh()

        for entry in entries:
            self.connect_message_listener(entry)
            self.connect_download_listener(entry)
            self.connect_integrity_listener(entry)
            self.connect_complete_listener(entry)

    def connect_message_listener(self, entry: FetchEntry):
        def listener(sender, message) -> None:
            self.current_entry = entry
            self.current_text.set_description_str(message, refresh=True)

        entry.status.on_message.connect(listener, weak=False)

    def connect_download_listener(self, entry: FetchEntry):
        def listener(sender, progress: Progress) -> None:
            self.current_bar.reset(max(entry.remote_entry.size, 1))

            def on_progress(sender, delta: int, new: int, old: int, completed: bool):
                self.current_bar.n = new
                self.current_bar.refresh()
                if not completed:
                    self.overall_bar.n = self.completed_bytes + new
                    self.overall_bar.refresh()

            progress.on_change.connect(on_progress, weak=False)

        entry.status.on_download.connect(listener, weak=False)

    def connect_integrity_listener(self, entry: FetchEntry):
        def listener(sender, progress: Progress) -> None:
            self.current_bar.reset(max(entry.remote_entry.size, 1))

            def on_progress(sender, delta: int, new: int, old: int, completed: bool):
                self.current_bar.n = new
                self.current_bar.refresh()

            progress.on_change.connect(on_progress, weak=False)

        entry.status.on_integrity_check.connect(listener, weak=False)

    def connect_complete_listener(self, entry: FetchEntry):
        def listener(sender) -> None:
            self.current_entry = entry
            self.completed_files += 1
            self.completed_bytes += entry.remote_entry.size
            self.overall_bar.n = self.completed_bytes
            self.overall_bar.refresh()

        entry.status.on_complete.connect(listener, weak=False)

    def create_progress_bars(self):
        self.overall_text = tqdm(
            total=0,
            position=0,
            dynamic_ncols=True,
            leave=False,
            bar_format="{desc}",
            desc=f"processing... (0/{self.total_files})",
        )
        self.overall_bar = tqdm(
            total=self.total_size,
            position=1,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            dynamic_ncols=True,
            leave=False,
            bar_format=("{percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}]"),
        )
        self.current_text = tqdm(
            total=0,
            position=2,
            dynamic_ncols=True,
            leave=False,
            bar_format="{desc}",
        )
        self.current_bar = tqdm(
            total=1,
            position=3,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            dynamic_ncols=True,
            leave=False,
            bar_format=(
                "{percentage:3.0f}%|{bar}| "
                "{n_fmt}/{total_fmt} "
                "[{elapsed}<{remaining}, {rate_fmt}]"
            ),
        )

    def __enter__(self):
        self.init()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        if exc_type is None and self.show_progress:
            self.report()
