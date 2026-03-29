from __future__ import annotations

from os import PathLike
import os
from typing import Sequence

from pathspec import PathSpec

from cli115.client import Client
from cli115.helpers import join_path


def upload(
    client: Client,
    local_path: str | PathLike[str],
    remote_path: str | PathLike[str],
    *,
    instant_only: int | None = None,
    include: Sequence[str] | None = None,
    exclude: Sequence[str] | None = None,
):
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
        client: Authenticated API client.
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
        result returned by ``client.file.upload`` when uploading a file.

    Raises:
        FileExistsError: If attempting to upload a directory to a remote file path.
        FileNotFoundError: Propagated from client calls when the remote entry is missing.
    """

    if os.path.isdir(local_path):
        return _upload_directory(
            client,
            local_path,
            remote_path,
            instant_only=instant_only,
            include=include,
            exclude=exclude,
        )

    # If remote path points to an existing directory, append the
    # local filename to form the final destination path.
    try:
        entry = client.file.stat(remote_path)
        if entry.is_directory:
            file_name = os.path.basename(local_path)
            remote_path = join_path(remote_path, file_name)
    except FileNotFoundError:
        pass

    return client.file.upload(
        remote_path,
        local_path,
        instant_only=instant_only,
    )


def _upload_directory(
    client: Client,
    local_path: str | PathLike[str],
    remote_path: str | PathLike[str],
    *,
    instant_only: int | None = None,
    include: Sequence[str] | None = None,
    exclude: Sequence[str] | None = None,
):
    local_path = os.path.abspath(local_path)
    remote_path = str(remote_path)

    try:
        entry = client.file.stat(remote_path)
        if not entry.is_directory:
            raise FileExistsError(
                f"cannot upload directory to a file path: {remote_path}"
            )
        # Remote exists as a directory: create a subdirectory with the local dir name.
        dir_name = os.path.basename(local_path)
        dest_path = join_path(remote_path, dir_name)
        dest_dir = client.file.create_directory(dest_path)
    except FileNotFoundError:
        # Remote does not exist: create it as the destination.
        dest_dir = client.file.create_directory(remote_path, parents=True)
        dest_path = remote_path

    include_spec = PathSpec.from_lines("gitignore", include) if include else None
    exclude_spec = PathSpec.from_lines("gitignore", exclude) if exclude else None

    files_to_upload = _collect_files(
        local_path, dest_path, include=include_spec, exclude=exclude_spec
    )
    dirs_to_create = _collect_dirs(files_to_upload, dest_path)

    for d in sorted(dirs_to_create):
        client.file.create_directory(d, parents=True)

    for local_file, remote_file in files_to_upload:
        client.file.upload(
            remote_file,
            local_file,
            instant_only=instant_only,
        )

    return dest_dir


def _collect_files(
    local_dir: str,
    remote_dir: str,
    *,
    include: PathSpec | None = None,
    exclude: PathSpec | None = None,
) -> list[tuple[str, str]]:
    """Return a sorted list of (local_path, remote_path) pairs under *local_dir*.

    Only regular files are included; directories are omitted (they are created
    separately).  *include_spec* and *exclude_spec* are matched against the
    path relative to *local_dir* using ``/`` separators.
    """
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
    """Return the set of unique remote parent directories implied by *files*.

    The *dest_path* directory itself is excluded since it has already been
    created by the caller.
    """
    dirs: set[str] = set()
    for _local, remote in files:
        parent = remote.rsplit("/", 1)[0]
        while parent and parent != dest_path:
            dirs.add(parent)
            parent = parent.rsplit("/", 1)[0]
    return dirs
