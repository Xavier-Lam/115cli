from __future__ import annotations

import os
from os import PathLike
from typing import Sequence

from blinker import Signal
from pathspec import PathSpec

from cli115.client import Client
from cli115.client.models import Directory, File, UploadStatus
from cli115.helpers import join_path


class UploadEntry:
    """A single file to be uploaded."""

    def __init__(
        self,
        local_path: str | PathLike[str],
        remote_path: str | PathLike[str],
    ):
        self.local_path = local_path
        self.remote_path = remote_path
        self.size = os.path.getsize(local_path) if os.path.isfile(local_path) else 0
        self.status = UploadStatus()


class Uploader:
    """Manages uploading files and directories to the remote filesystem.

    The constructor takes the authenticated client. Call :meth:`upload`
    to queue and upload a local file or directory to a remote path.

    Attributes:
        entries: List of :class:`UploadEntry` objects queued for upload.
        on_entry_added: Signal emitted when new entries are added.
            Receivers get ``(sender, entries=<list of new entries>)``.
    """

    def __init__(self, client: Client, *, dry_run: bool = False):
        self._client = client
        self.dry_run = dry_run
        self.entries: list[UploadEntry] = []
        self.on_entry_added = Signal()

    def upload(
        self,
        local_path: str | os.PathLike[str],
        remote_path: str,
        *,
        instant_only: int | None = None,
        include: Sequence[str] | None = None,
        exclude: Sequence[str] | None = None,
        no_target_dir: bool = False,
    ) -> None:
        """Upload a local file or directory to the remote filesystem.

        If ``local_path`` is a directory, the directory tree is uploaded
        recursively into ``remote_path``. If ``local_path`` is a file and
        ``remote_path`` points to an existing remote directory, the local
        filename is appended to the destination path. Uses ``client.file.upload``
        and ``client.file.create_directory`` under the hood.

        When uploading a directory, ``include`` and ``exclude`` glob patterns
        control which files are transferred.  Patterns follow the gitignore /
        VS Code glob syntax — for example ``"**/*.log"`` excludes all log files
        and ``"temp/**"`` excludes the ``temp/`` subtree.  See
        https://code.visualstudio.com/docs/editor/glob-patterns for the full
        syntax reference.  Patterns are matched against paths relative to the
        root of the uploaded directory (using ``/`` separators).

        Args:
            local_path: Path to the local file or directory.
            remote_path: Destination path on the remote.
            instant_only: If set to a byte threshold (e.g. ``100 * 1024 * 1024``
                for 100 MB), files at or above that size will be forced to use
                instant upload only.  Values below
                :data:`~cli115.client.base.MIN_INSTANT_UPLOAD_SIZE` (2 MB) are
                ignored.  Raises
                :class:`~cli115.exceptions.InstantUploadNotAvailableError` when
                instant upload is unavailable for a qualifying file.
            include: Glob patterns for files to include.  Only files matching at
                least one pattern are uploaded.  ``None`` means include all files.
            exclude: Glob patterns for files to exclude.  Files matching any
                pattern are skipped.  ``None`` means exclude nothing.
        Returns:
            The created remote directory entry when uploading a directory, or the
            result returned by ``client.file.upload`` when uploading a file. `None`
            is returned when ``dry_run`` is ``True``.

        Raises:
            FileExistsError: If attempting to upload a directory to a remote file path.
            FileNotFoundError: If the target remote directory does not exist.
        """

        local_path = os.path.abspath(local_path)
        if os.path.isdir(local_path):
            return self._upload_directory(
                local_path,
                remote_path,
                instant_only=instant_only,
                include=include,
                exclude=exclude,
                no_target_dir=no_target_dir,
            )
        else:
            return self._upload_file(
                local_path,
                remote_path,
                instant_only=instant_only,
            )

    def _upload_file(
        self,
        local_path: str,
        remote_path: str,
        *,
        instant_only: int | None,
    ) -> File | None:
        # If remote path points to an existing directory, append filename
        try:
            entry = self._client.file.stat(remote_path)
            if entry.is_directory:
                file_name = os.path.basename(local_path)
                remote_path = join_path(remote_path, file_name)
        except FileNotFoundError:
            pass

        upload_entry = UploadEntry(local_path, remote_path)
        self.entries.append(upload_entry)
        self.on_entry_added.send(self, entries=[upload_entry])

        if not self.dry_run:
            return self._client.file.upload(
                remote_path,
                local_path,
                instant_only=instant_only,
                status=upload_entry.status,
            )

    def _upload_directory(
        self,
        local_path: str,
        remote_path: str,
        *,
        no_target_dir: bool = False,
        instant_only: int | None,
        include: PathSpec | None,
        exclude: PathSpec | None,
    ) -> Directory | None:
        entry = None
        dest_path = remote_path
        try:
            entry = self._client.file.stat(remote_path)
            if not entry.is_directory:
                raise FileExistsError(
                    f"cannot upload directory to a file path: {remote_path}"
                )
            # Remote exists as a directory: create a subdirectory with the local dir name.
            if not no_target_dir:
                dir_name = os.path.basename(local_path)
                dest_path = join_path(remote_path, dir_name)
        except FileNotFoundError:
            pass

        include_spec = PathSpec.from_lines("gitignore", include) if include else None
        exclude_spec = PathSpec.from_lines("gitignore", exclude) if exclude else None

        # Collect files to upload
        files = _collect_files(
            local_path,
            dest_path,
            include=include_spec,
            exclude=exclude_spec,
        )
        dirs = _collect_dirs(files, dest_path)

        entries = [UploadEntry(lf, rf) for lf, rf in files]
        self.entries.extend(entries)
        self.on_entry_added.send(self, entries=entries)

        if self.dry_run:
            return

        # Create destination directory
        dest_dir = self._client.file.create_directory(dest_path, parents=entry is None)

        # Create intermediate directories
        for d in sorted(dirs):
            self._client.file.create_directory(d, parents=True)

        # Upload files
        for upload_entry in entries:
            self._client.file.upload(
                upload_entry.remote_path,
                upload_entry.local_path,
                instant_only=instant_only,
                status=upload_entry.status,
            )

        return dest_dir


def _collect_files(
    local_dir: str,
    remote_dir: str,
    *,
    include: PathSpec | None = None,
    exclude: PathSpec | None = None,
) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for root, dirs, fnames in os.walk(local_dir):
        dirs.sort()
        rel_root = os.path.relpath(root, local_dir).replace("\\", "/")
        if rel_root == ".":
            rel_root = ""
        for fname in sorted(fnames):
            rel_path = f"{rel_root}/{fname}" if rel_root else fname
            if include is not None and not include.match_file(rel_path):
                continue
            if exclude is not None and exclude.match_file(rel_path):
                continue
            local_file = os.path.join(root, fname)
            remote_file = join_path(remote_dir, rel_path)
            result.append((local_file, remote_file))
    return result


def _collect_dirs(files: list[tuple[str, str]], dest_path: str) -> set[str]:
    dirs: set[str] = set()
    for _local, remote in files:
        parent = remote.rsplit("/", 1)[0]
        while parent and parent != dest_path:
            dirs.add(parent)
            parent = parent.rsplit("/", 1)[0]
    return dirs
