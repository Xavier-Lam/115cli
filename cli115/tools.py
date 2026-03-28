from os import PathLike
import os

from cli115.client import Client
from cli115.exceptions import AlreadyExistsError, NotFoundError


def upload(
    client: Client,
    local_path: str | PathLike[str],
    remote_path: str | PathLike[str],
    *,
    instant_only: bool = False,
):
    """Upload a local file or directory to the remote filesystem.

    If ``local_path`` is a directory, the directory tree is uploaded
    recursively into ``remote_path``. If ``local_path`` is a file and
    ``remote_path`` points to an existing remote directory, the local
    filename is appended to the destination path. Uses ``client.file.upload``
    and ``client.file.create_directory`` under the hood.

    Args:
        client (Client): Authenticated API client.
        local_path (str | PathLike[str]): Path to the local file or directory.
        remote_path (str | PathLike[str]): Destination path on the remote.
        instant_only (bool): If True, only attempt instant uploads.

    Returns:
        The created remote directory entry when uploading a directory, or the
        result returned by ``client.file.upload`` when uploading a file.

    Raises:
        AlreadyExistsError: If attempting to upload a directory to a remote file path.
        NotFoundError: Propagated from client calls when the remote entry is missing.
    """

    if os.path.isdir(local_path):
        return _upload_directory(
            client, local_path, remote_path, instant_only=instant_only
        )

    # If remote path points to an existing directory, append the
    # local filename to form the final destination path.
    try:
        entry = client.file.stat(remote_path)
        if entry.is_directory:
            file_name = os.path.basename(local_path)
            remote_path = remote_path.rstrip("/") + "/" + file_name
    except NotFoundError:
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
    instant_only: bool = False,
):
    local_path = os.path.abspath(local_path)
    remote_path = str(remote_path)

    try:
        entry = client.file.stat(remote_path)
        if not entry.is_directory:
            raise AlreadyExistsError(
                f"Cannot upload directory to a file path: {remote_path}"
            )
        # Remote exists as a directory: create a subdirectory with the local dir name.
        dir_name = os.path.basename(local_path)
        dest_path = remote_path.rstrip("/") + "/" + dir_name
        dest_dir = client.file.create_directory(dest_path)
    except NotFoundError:
        # Remote does not exist: create it as the destination.
        dest_dir = client.file.create_directory(remote_path, parents=True)
        dest_path = remote_path

    _upload_tree(client, local_path, dest_path, instant_only=instant_only)
    return dest_dir


def _upload_tree(
    client: Client,
    local_dir: str,
    remote_dir: str,
    *,
    instant_only: bool = False,
):
    for entry in sorted(os.scandir(local_dir), key=lambda e: e.name):
        remote_item = remote_dir.rstrip("/") + "/" + entry.name
        if entry.is_dir():
            client.file.create_directory(remote_item, parents=True)
            _upload_tree(client, entry.path, remote_item, instant_only=instant_only)
        else:
            client.file.upload(remote_item, entry.path, instant_only=instant_only)
