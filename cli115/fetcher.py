from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
from os import PathLike
from typing import Sequence

from blinker import Signal
from pathspec import PathSpec

from cli115.client import Client
from cli115.client.models import Directory, File, Progress
from cli115.helpers import sha1_file

DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024


class DownloadStatus:
    def __init__(self) -> None:
        self._is_completed: bool = False
        self.on_message: Signal = Signal()
        self.on_download: Signal = Signal()
        self.on_integrity_check: Signal = Signal()
        self.on_complete: Signal = Signal()

    @property
    def is_completed(self) -> bool:
        return self._is_completed

    def set_message(self, message: str) -> None:
        self.on_message.send(self, message=message)

    @contextmanager
    def start_download(self, file_size: int):
        progress = Progress(file_size)
        self.on_download.send(self, progress=progress)
        self.set_message("downloading...")
        yield progress

    @contextmanager
    def start_integrity_check(self, file_size: int):
        progress = Progress(file_size)
        self.on_integrity_check.send(self, progress=progress)
        self.set_message("checking file integrity...")
        yield progress

    def complete(self) -> None:
        if not self._is_completed:
            self._is_completed = True
            self.on_complete.send(self)
            self.set_message("download completed")


class FetchEntry:
    """A single file to be downloaded."""

    def __init__(
        self,
        remote_entry: File,
        local_path: str | PathLike[str],
    ):
        self.remote_entry = remote_entry
        self.local_path = local_path
        self.status = DownloadStatus()
        self.error: Exception | None = None


class Fetcher:
    """Manages downloading files and directories from remote filesystem."""

    def __init__(
        self,
        client: Client,
        *,
        dry_run: bool = False,
        user_agent: str | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ):
        self._client = client
        self.dry_run = dry_run
        self.user_agent = user_agent
        self.chunk_size = chunk_size
        self.entries: list[FetchEntry] = []
        self.on_entry_added = Signal()

    def fetch(
        self,
        remote_entry: Directory | File,
        local_path: str | os.PathLike[str],
        *,
        check_integrity: bool = False,
        include: Sequence[str] | None = None,
        exclude: Sequence[str] | None = None,
    ) -> str | None:
        """Fetch a remote file or directory to a local destination path.

        Args:
            remote_entry: Remote file or directory entry to fetch.
            local_path: Local destination path. For files, this is the output
                file path. For directories, this is the destination directory.
            check_integrity: When ``True``, verify downloaded files by size and
                SHA-1.
            include: Optional glob patterns used to include files when fetching
                a directory.
            exclude: Optional glob patterns used to exclude files when fetching
                a directory.

        Returns:
            The resolved local destination path, or ``None`` in dry-run mode.

        Raises:
            FileExistsError: If fetching a directory to an existing local file
                path.
            CommandLineError: If integrity checks fail for a downloaded file.
        """

        local_path = os.path.abspath(local_path)
        if remote_entry.is_directory:
            self._fetch_directory(
                remote_entry,
                local_path,
                check_integrity=check_integrity,
                include=include,
                exclude=exclude,
            )
        else:
            self._fetch_file(
                remote_entry,
                local_path,
                check_integrity=check_integrity,
            )
        if not self.dry_run:
            return local_path

    def _fetch_file(
        self,
        remote_entry: File,
        local_path: str | os.PathLike[str],
        *,
        check_integrity: bool = False,
    ) -> str | None:
        entry = FetchEntry(remote_entry, local_path)
        self.entries.append(entry)
        self.on_entry_added.send(self, entries=[entry])

        if not self.dry_run:
            self._download_entry(
                remote_entry,
                local_path,
                check_integrity=check_integrity,
                status=entry.status,
            )

    def _fetch_directory(
        self,
        remote_entry: Directory,
        dest_path: str | os.PathLike[str],
        *,
        check_integrity: bool = False,
        include: Sequence[str] | None = None,
        exclude: Sequence[str] | None = None,
    ) -> str | None:
        if os.path.isfile(dest_path):
            raise FileExistsError(f"cannot fetch directory to a file path: {dest_path}")

        include_spec = PathSpec.from_lines("gitignore", include) if include else None
        exclude_spec = PathSpec.from_lines("gitignore", exclude) if exclude else None

        files = self._collect_files(
            remote_entry,
            include=include_spec,
            exclude=exclude_spec,
        )
        entries = [
            FetchEntry(
                remote_file,
                os.path.join(dest_path, rel_path),
            )
            for remote_file, rel_path in files
        ]
        self.entries.extend(entries)
        self.on_entry_added.send(self, entries=entries)

        if not self.dry_run:
            for entry in entries:
                try:
                    self._download_entry(
                        entry.remote_entry,
                        entry.local_path,
                        check_integrity=check_integrity,
                        status=entry.status,
                    )
                except Exception as exc:
                    entry.error = exc

    def _download_entry(
        self,
        entry: File,
        local_path: str | os.PathLike[str],
        *,
        check_integrity: bool,
        status: DownloadStatus,
    ) -> None:
        parent = os.path.dirname(local_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        try:
            with (
                self._client.file.open(
                    entry,
                    user_agent=self.user_agent,
                ) as remote,
                open(local_path, "w+b") as local_file,
                ThreadPoolExecutor(max_workers=1) as pool,
                status.start_download(entry.size) as progress,
            ):
                remote.set_stream(True)
                write_future = None

                while True:
                    chunk = remote.read(self.chunk_size)
                    if write_future is not None:
                        write_future.result()
                    if not chunk:
                        break
                    progress.update(len(chunk))
                    write_future = pool.submit(local_file.write, chunk)

                if write_future is not None:
                    write_future.result()

                status.complete()

                if check_integrity:
                    with (
                        status.start_integrity_check(entry.size) as progress,
                        progress.patch_file(local_file),
                    ):
                        sha1, size = sha1_file(local_file)
                    if size != entry.size:
                        raise ValueError(
                            f"size mismatch: expected {entry.size}, got {size}"
                        )
                    if sha1 != entry.sha1:
                        raise ValueError(
                            f"sha1 mismatch: expected {entry.sha1}, got {sha1}"
                        )
                    status.set_message("file integrity verified")
        except:
            os.path.exists(local_path) and os.unlink(local_path)
            raise

    def _collect_files(
        self,
        remote_entry: Directory,
        *,
        include: PathSpec | None,
        exclude: PathSpec | None,
    ) -> list[tuple[File, str]]:
        rv: list[tuple[File, str]] = []

        def walk(current: Directory, rel_root: str) -> None:
            for child in self._client.file.list(current):
                rel_path = os.path.join(rel_root, child.name)
                if child.is_directory:
                    walk(child, rel_path)
                    continue

                if include is not None and not include.match_file(rel_path):
                    continue
                if exclude is not None and exclude.match_file(rel_path):
                    continue

                rv.append((child, rel_path))

        walk(remote_entry, "")
        return rv
