"""Upload command."""

from __future__ import annotations

import argparse
import os
from threading import Event, Thread
import time

from tqdm import tqdm

from cli115.client.models import Progress
from cli115.cmds.base import BaseCommand
from cli115.cmds.formatter import PairFormatterMixin, format_entry
from cli115.exceptions import CommandLineError
from cli115.helpers import format_size, parse_size
from cli115.uploader import UploadEntry, Uploader


class UploadCommand(PairFormatterMixin, BaseCommand):
    """Upload a local file or directory to the remote path."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
        parser.add_argument("local_path", help="local file or directory path")
        parser.add_argument("remote_path", help="remote destination path")
        parser.add_argument(
            "--plan",
            action="store_true",
            default=False,
            help="Show planned files before uploading",
        )
        parser.add_argument(
            "--instant-only",
            type=parse_size,
            default=None,
            metavar="SIZE",
            help=(
                "Force instant (hash-based) upload for files at or above SIZE "
                "(e.g. '100MB', '1GB').  Raises an error if the server does not "
                "have a matching copy.  Values below 2 MB are ignored."
            ),
        )
        parser.add_argument(
            "--include",
            action="append",
            default=None,
            metavar="PATTERN",
            help=(
                "Glob pattern for files to include when uploading a directory "
                "(may be repeated; only matching files are uploaded)"
            ),
        )
        parser.add_argument(
            "--exclude",
            action="append",
            default=None,
            metavar="PATTERN",
            help=(
                "Glob pattern for files to exclude when uploading a directory "
                "(may be repeated; matching files are skipped)"
            ),
        )
        parser.add_argument(
            "-T",
            "--no-target-directory",
            action="store_true",
            default=False,
            help=(
                "Treat remote_path as the exact destination rather than a "
                "directory to upload into (never append the local name)"
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Only show files that would be uploaded without uploading",
        )
        parser.add_argument(
            "-s",
            "--silent",
            action="store_true",
            default=False,
            help="Do not report progress, only print the final result",
        )

    def execute(self, args: argparse.Namespace) -> None:
        uploader = Uploader(self._create_client(), dry_run=args.dry_run)

        done = Event()
        state: dict[str, object] = {}

        def worker() -> None:
            try:
                state["result"] = uploader.upload(
                    args.local_path,
                    args.remote_path,
                    instant_only=args.instant_only,
                    include=args.include,
                    exclude=args.exclude,
                    no_target_dir=args.no_target_directory,
                )
            except BaseException as exc:
                state["error"] = exc
            finally:
                done.set()

        with UploadProgress(
            uploader,
            show_plan=args.plan or args.dry_run,
            show_progress=not args.silent and not args.dry_run,
        ):
            Thread(target=worker, daemon=True, name="upload-worker").start()

            try:
                while not done.wait(timeout=0.1):
                    pass
            except KeyboardInterrupt as exc:
                raise CommandLineError("upload cancelled by user") from exc

        error = state.get("error")
        if isinstance(error, BaseException):
            raise error

        failed_entries = [
            entry for entry in uploader.entries if entry.error is not None
        ]
        self.warn("{0} file(s) failed to upload".format(len(failed_entries)))
        for entry in failed_entries:
            self.warn(
                "- {0} -> {1}: {2}".format(
                    os.fspath(entry.local_path),
                    entry.remote_path,
                    entry.error,
                )
            )

        if state.get("result"):
            self.output(format_entry(state["result"]), args)


class UploadProgress:
    def __init__(
        self,
        uploader: Uploader,
        *,
        show_plan: bool = False,
        show_progress: bool = True,
    ):
        self.uploader = uploader
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
        self.instant_count = 0

        self._current_entry: UploadEntry | None = None

    @property
    def current_entry(self) -> UploadEntry | None:
        return self._current_entry

    @current_entry.setter
    def current_entry(self, entry: UploadEntry) -> None:
        if not (self._current_entry is entry):
            self._current_entry = entry

            self.current_bar.reset(max(entry.size, 1))

            self.overall_text.set_description_str(
                "{0} ({1}/{2})".format(
                    entry.local_path,
                    self.completed_files,
                    self.total_files,
                ),
                refresh=True,
            )

    def init(self):
        self.uploader.on_entry_added.connect(self.on_added)
        self.started_at = time.monotonic()

    def close(self):
        self.ended_at = time.monotonic()
        if self.overall_bar:
            self.current_text.close()
            self.current_bar.close()
            self.overall_text.close()
            self.overall_bar.close()
            print()  # ensure progress bars are cleared before final output

    def report(self):
        if self.started_at is None or self.ended_at is None:
            return

        self.ended_at = time.monotonic()
        elapsed = self.ended_at - self.started_at
        tqdm.write(
            "Upload finished in {0:.1f}s: {1} total, {2} of {3} files instantly uploaded".format(
                elapsed,
                format_size(self.total_size),
                self.instant_count,
                self.total_files,
            )
        )

    def on_added(self, sender, **kw):
        entries: list[UploadEntry] = kw["entries"]
        if self.show_plan:
            for idx, entry in enumerate(entries):
                print(
                    "{0}. {1} -> {2} ({3})".format(
                        idx,
                        os.fspath(entry.local_path),
                        entry.remote_path,
                        format_size(entry.size),
                    )
                )

        if not self.show_progress:
            return

        self.total_files = len(entries)
        self.total_size = max(sum(e.size for e in entries), 1)
        self.create_progress_bars()

        for entry in entries:
            self.connect_message_listener(entry)
            self.connect_upload_listener(entry)
            self.connect_complete_listener(entry)

    def connect_message_listener(self, entry: UploadEntry):
        def listener(sender, message) -> None:
            self.current_entry = entry
            self.current_text.set_description_str(message, refresh=True)

        entry.status.on_message.connect(listener, weak=False)

    def connect_upload_listener(self, entry: UploadEntry):
        def listener(sender, progress: Progress) -> None:
            self.current_bar.reset(max(entry.size, 1))

            def on_progress(sender, delta: int, new: int, old: int, completed: bool):
                self.current_bar.n = new
                self.current_bar.refresh()
                if not completed:
                    self.overall_bar.n = self.completed_bytes + new
                    self.overall_bar.refresh()

            progress.on_change.connect(on_progress, weak=False)

        entry.status.on_upload.connect(listener, weak=False)

    def connect_complete_listener(self, entry: UploadEntry):
        def listener(sender) -> None:
            self.current_entry = entry

            self.completed_files += 1
            if entry.status.is_instant_uploaded:
                self.instant_count += 1

            self.completed_bytes += entry.size
            self.overall_bar.n = self.completed_bytes
            self.overall_bar.refresh()

        entry.status.on_complete.connect(listener, weak=False)

    def create_progress_bars(self):
        self.overall_text = tqdm(
            total=0,
            position=0,
            dynamic_ncols=True,
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
            total=0, position=2, dynamic_ncols=True, leave=False, bar_format="{desc}"
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
