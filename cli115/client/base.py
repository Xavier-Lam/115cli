"""Client interface definitions for cli115."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import fields
from os import PathLike
from typing import BinaryIO, Callable

import httpx

from cli115.client.models import (
    AccountInfo,
    CloudTask,
    Directory,
    DownloadInfo,
    DownloadQuota,
    File,
    FileSystemEntry,
    Pagination,
    Progress,
    SortField,
    SortOrder,
)


DEFAULT_PAGE_SIZE = 115  # Default number of items to return in list operations
MAX_PAGE_SIZE = 1150  # 1150 is the maximum page size allowed by the API
MIN_INSTANT_UPLOAD_SIZE = 2 * 1024 * 1024  # Minimum file size for instant upload


class Client(ABC):
    """Abstract high-level client interface."""

    @property
    @abstractmethod
    def account(self) -> AccountClient:
        """Access account operations."""

    @property
    @abstractmethod
    def file(self) -> FileClient:
        """Access file operations."""

    @property
    @abstractmethod
    def download(self) -> DownloadClient:
        """Access cloud download (offline) operations."""


class AccountClient(ABC):
    """Abstract interface for account operations."""

    @abstractmethod
    def info(self) -> AccountInfo:
        """Get account information for the authenticated user.

        Returns:
            An AccountInfo with user name, user ID, VIP status and expiry.
        """


class DownloadClient(ABC):
    """Abstract interface for cloud download (offline) operations."""

    @abstractmethod
    def quota(self) -> DownloadQuota:
        """Get cloud download quota information.

        Returns:
            A DownloadQuota with remaining and total quota.
        """

    @abstractmethod
    def list(self, page: int = 1) -> tuple[list[CloudTask], Pagination]:
        """List cloud download tasks.

        Args:
            page: Page number (1-based).

        Returns:
            A tuple of (tasks, pagination).
        """

    @abstractmethod
    def add_url(
        self, url: str, *, dest_dir: str | Directory | None = None
    ) -> CloudTask:
        """Add a single URL as a cloud download task.

        Args:
            url: Download URL, magnet link, or ed2k link.
            dest_dir: Optional destination directory path or
                :class:`Directory` object. If ``None``, uses the
                default cloud download folder.

        Returns:
            The created CloudTask.
        """

    @abstractmethod
    def add_urls(
        self, *urls: str, dest_dir: str | Directory | None = None
    ) -> list[CloudTask]:
        """Add multiple URLs as cloud download tasks.

        Args:
            urls: Download URLs.
            dest_dir: Optional destination directory path or
                :class:`Directory` object. If ``None``, uses the
                default cloud download folder.

        Returns:
            A list of created CloudTask objects.
        """

    @abstractmethod
    def delete(self, *task_hashes: str) -> None:
        """Delete cloud download tasks.

        Args:
            task_hashes: info_hash values of tasks to delete.
        """


class FileClient(ABC):
    """Abstract interface for file operations."""

    @abstractmethod
    def list(
        self,
        path: str | Directory = "/",
        *,
        sort: SortField = SortField.FILENAME,
        sort_order: SortOrder = SortOrder.ASC,
        limit: int = 115,
        offset: int = 0,
    ) -> tuple[list[Directory | File], Pagination]:
        """List files and directories under the given path.

        Args:
            path: Directory path or :class:`Directory` object. ``"/"`` for root.
            sort: Sort field.
            sort_order: :attr:`SortOrder.ASC` or :attr:`SortOrder.DESC`.
            limit: Maximum number of items to return.
            offset: Pagination offset.

        Returns:
            A tuple of (items, pagination).
        """

    @abstractmethod
    def find(
        self,
        query: str,
        *,
        path: str | Directory | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> tuple[list[Directory | File], Pagination]:
        """Search for files and directories matching a query.

        Args:
            query: Search string.
            path: Directory to search within. ``None`` for a global search.
            limit: Maximum number of items to return.
            offset: Pagination offset.

        Returns:
            A tuple of (items, pagination).
        """

    @abstractmethod
    def id(self, file_id: str) -> Directory | File:
        """Get info for a file or directory by its ID.

        Prefer this over other methods when the ID is already known,
        as it requires fewer requests than resolving by path.

        Args:
            file_id: The unique identifier of the file or directory.

        Returns:
            A Directory or File object.
        """

    @abstractmethod
    def info(self, path: str) -> Directory | File:
        """Get info for a file or directory at the given path.

        Args:
            path: Path to the file or directory.

        Returns:
            A Directory or File object.
        """

    @abstractmethod
    def create_directory(self, path: str, *, parents: bool = False) -> Directory:
        """Create a new directory.

        Args:
            path: Absolute path of the directory to create
                  (e.g. ``"/photos/vacation"``).
            parents: If ``True``, create any missing parent directories
                     automatically (like ``mkdir -p``). If ``False`` (default),
                     raise :class:`~cli115.exceptions.NotFoundError` when the
                     parent does not exist.

        Returns:
            The created Directory.
        """

    def upload(
        self,
        path: str,
        file: str | PathLike[str] | BinaryIO,
        *,
        instant_only: bool = False,
        progress_callback: Callable[[Progress], object] | None = None,
    ) -> File:
        """Upload a file.

        Instant upload is always attempted first when the file is at
        least :data:`MIN_INSTANT_UPLOAD_SIZE` bytes: if the server already has
        a copy matched by SHA-1, the upload completes without transferring data.

        Args:
            path: Full destination path on the remote disk, including the
                  target filename (e.g. ``"/backups/archive.tar.gz"``). The
                  parent directory must already exist.
            file: A local file path (str / PathLike) or a readable
                  binary file-like object.
            instant_only: If ``True``, only attempt instant upload for files
                  at or above :data:`MIN_INSTANT_UPLOAD_SIZE`.  Files below
                  that threshold are uploaded normally.  Raises
                  :class:`~cli115.exceptions.InstantUploadNotAvailableError`
                  when instant upload is unavailable for a large-enough file.
            progress_callback: Optional callable invoked periodically
                  with a :class:`Progress` instance.

        Returns:
            The uploaded File entry.
        """
        opened = None
        if isinstance(file, (str, PathLike)):
            opened = open(file, "rb")
            file = opened
        try:
            return self._upload(
                path,
                file,
                instant_only=instant_only,
                progress_callback=progress_callback,
            )
        finally:
            if opened is not None:
                opened.close()

    @abstractmethod
    def _upload(
        self,
        path: str,
        file: BinaryIO,
        *,
        instant_only: bool = False,
        progress_callback: Callable[[Progress], object] | None = None,
    ) -> File:
        """Perform the actual file upload.

        Subclasses implement this method. The caller guarantees that *file*
        is a readable binary file-like object (i.e. path strings have already
        been opened before this method is invoked).

        Args:
            path: Full destination path on the remote disk.
            file: A readable binary file-like object.
            instant_only: See :meth:`upload`.
            progress_callback: See :meth:`upload`.

        Returns:
            The uploaded File entry.
        """

    @abstractmethod
    def delete(self, path: str | FileSystemEntry, *, recursive: bool = False) -> None:
        """Delete a file or directory (moves to recycle bin).

        Args:
            path: Path to the item to delete.
            recursive: If ``True`` (default), delete the item even when it is a
                       non-empty directory. If ``False``, raise
                       :class:`~cli115.exceptions.DirectoryNotEmptyError` when
                       the directory contains children.
        """

    @abstractmethod
    def batch_delete(
        self, *paths: str | FileSystemEntry, recursive: bool = False
    ) -> None:
        """Delete multiple files/directories.

        Args:
            paths: Paths of items to delete.
            recursive: If ``True`` (default), delete the items even when they are
                       non-empty directories. If ``False``, raise
                       :class:`~cli115.exceptions.DirectoryNotEmptyError` when
                       any directory contains children.
        """

    @abstractmethod
    def rename(self, path: str | FileSystemEntry, name: str) -> None:
        """Rename a file or directory.

        Args:
            path: Path to the item to rename.
            name: New name.
        """

    @abstractmethod
    def move(self, src: str | FileSystemEntry, dest_dir: str | Directory) -> None:
        """Move a file or directory to a destination folder.

        Args:
            src: Path to the item to move.
            dest_dir: Destination directory path or :class:`Directory` object.
        """

    @abstractmethod
    def batch_move(
        self, *srcs: str | FileSystemEntry, dest_dir: str | Directory
    ) -> None:
        """Move multiple items to a destination folder.

        Args:
            srcs: Paths of items to move.
            dest_dir: Destination directory path or :class:`Directory` object.
        """

    @abstractmethod
    def copy(self, src: str | FileSystemEntry, dest_dir: str | Directory) -> None:
        """Copy a file or directory to a destination folder.

        Args:
            src: Path to the item to copy.
            dest_dir: Destination directory path or :class:`Directory` object.
        """

    @abstractmethod
    def batch_copy(
        self, *srcs: str | FileSystemEntry, dest_dir: str | Directory
    ) -> None:
        """Copy multiple items to a destination folder.

        Args:
            srcs: Paths of items to copy.
            dest_dir: Destination directory path or :class:`Directory` object.
        """

    @abstractmethod
    def download_info(
        self, path: str | File, *, user_agent: str | None = None
    ) -> DownloadInfo:
        """Get download information for an existing file.

        Args:
            path: Path to the file or a :class:`File` object.
            user_agent: Custom User-Agent string for the download request.
                If ``None``, uses :data:`DEFAULT_USER_AGENT`.

        Returns:
            A DownloadInfo with URL, user-agent, cookies, and file metadata.
        """

    def open(self, path: str | File) -> RemoteFile:
        """Get a lazy file-like object for a remote file.

        The returned :class:`RemoteFile` supports ``read``, ``seek`` and
        ``tell``.  Content is only downloaded when :meth:`~RemoteFile.read`
        is called, and Range headers are used for partial reads.

        Args:
            path: Path to the file or a :class:`File` object.

        Returns:
            A :class:`RemoteFile` wrapping the download URL.
        """
        info = self.download_info(path)
        return RemoteFile(info)


class LazyPathMixin:
    """Mixin that lazily resolves the ``path`` attribute by walking up the
    parent-directory chain via the ``id()`` method.

    Attach a ``FileClient`` instance to ``_file_client`` after construction.
    When ``.path`` is first accessed and is ``None``, the mixin calls
    ``_file_client.id(parent_id)`` recursively up to the root and caches the
    resulting absolute path string so the walk only happens once.
    """

    _file_client = None

    @property
    def path(self):
        val = self.__dict__.get("path")
        if val is not None:
            return val
        parts = [self.name]
        parent_id = self.parent_id
        while parent_id and parent_id != "0":
            parent = self._file_client.id(parent_id)
            parts.append(parent.name)
            parent_id = parent.parent_id
        val = "/" + "/".join(reversed(parts))
        self.__dict__["path"] = val
        return val

    @path.setter
    def path(self, value):
        pass  # ignore attempts to set path directly


def new_lazy_cls(item: FileSystemEntry, client: FileClient) -> FileSystemEntry:
    cls = item.__class__
    cls = type(cls.__name__, (LazyPathMixin, cls), {})
    attrs = {f.name: getattr(item, f.name) for f in fields(item)}
    rv = cls(**attrs)
    rv._file_client = client
    return rv


class RemoteFile:
    """A file-like object that lazily reads content from a remote URL.

    By default, Range headers are used for partial reads.  Call
    :meth:`set_stream` to switch to httpx streaming mode, which reads the
    file sequentially via :meth:`httpx.Response.iter_bytes` without using
    Range headers.
    """

    def __init__(self, info: DownloadInfo) -> None:
        self._info = info
        self._pos = 0
        self._size = info.file_size
        self._client = None
        self._stream = False
        self._stream_context = None
        self._stream_resp = None
        self._stream_iter = None

    # -- helpers --

    def _ensure_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers={
                    "User-Agent": self._info.user_agent,
                    "Cookie": self._info.cookies,
                    "Referer": self._info.referer,
                },
                follow_redirects=True,
            )
        return self._client

    def _ensure_stream(self):
        if self._stream_context is None:
            client = self._ensure_client()
            self._stream_context = client.stream("GET", self._info.url)
            resp = self._stream_context.__enter__()
            resp.raise_for_status()
            self._stream_resp = resp
        return self._stream_resp

    def _close_stream(self) -> None:
        if self._stream_context is not None:
            self._stream_context.__exit__(None, None, None)
            self._stream_context = None
            self._stream_resp = None
            self._stream_iter = None

    # -- stream flag --

    def set_stream(self, enable: bool) -> None:
        """Enable or disable httpx streaming mode.

        When enabled, :meth:`read` uses :meth:`httpx.Response.iter_bytes`
        instead of Range headers.  Disabling after a stream has been opened
        closes the active stream.
        """
        self._stream = enable
        if not enable:
            self._close_stream()

    # -- file-like interface --

    @property
    def name(self) -> str:
        return self._info.file_name

    @property
    def size(self) -> int:
        return self._size

    def readable(self) -> bool:
        return True

    def writable(self) -> bool:
        return False

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._pos = offset
        elif whence == 1:
            self._pos += offset
        elif whence == 2:
            self._pos = self._size + offset
        else:
            raise ValueError(f"invalid whence: {whence}")
        self._pos = max(0, min(self._pos, self._size))
        return self._pos

    def read(self, size: int = -1) -> bytes:
        if self._pos >= self._size:
            return b""
        if self._stream:
            resp = self._ensure_stream()
            if self._stream_iter is None:
                self._stream_iter = resp.iter_bytes(size if size > 0 else None)
            data = next(self._stream_iter, b"")
            self._pos += len(data)
            return data
        client = self._ensure_client()
        start = self._pos
        if size < 0:
            end = self._size - 1
        else:
            end = min(start + size - 1, self._size - 1)
        headers = {"Range": f"bytes={start}-{end}"}
        resp = client.get(self._info.url, headers=headers)
        resp.raise_for_status()
        data = resp.content
        self._pos += len(data)
        return data

    def close(self) -> None:
        self._close_stream()
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
