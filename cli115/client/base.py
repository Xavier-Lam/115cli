"""Client interface definitions for cli115."""

from __future__ import annotations

from abc import ABC, abstractmethod
from os import PathLike
from typing import BinaryIO, Callable, Sequence

import httpx

from cli115.client.models import (
    AccountInfo,
    CloudTask,
    Directory,
    DownloadUrl,
    DownloadQuota,
    File,
    FileSystemEntry,
    Pagination,
    Progress,
    SortField,
    SortOrder,
    TaskFilter,
    Usage,
)
from cli115.client.lazy import LazyPathCollection, LazyCollection


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

    @abstractmethod
    def usage(self) -> Usage:
        """Get disk storage usage information.

        Returns:
            A StorageInfo with total, used, and remaining storage in bytes.
        """


class DownloadClient(ABC):
    """Abstract interface for cloud download (offline) operations."""

    @abstractmethod
    def quota(self) -> DownloadQuota:
        """Get cloud download quota information.

        Returns:
            A DownloadQuota with remaining and total quota.
        """

    def list(self, filter: TaskFilter | None = None) -> Sequence[CloudTask]:
        """Return a lazy collection of all cloud download tasks.

        Warning: Avoid fully loading all tasks if you don't know the total
        number of items, as this will trigger many API requests.
        """
        return LazyCollection(
            lambda page, page_size: self._list(
                page=page,
                page_size=page_size,
                filter=filter,
            ),
            page_size=DEFAULT_PAGE_SIZE,
        )

    @abstractmethod
    def _list(
        self, page: int = 1, page_size: int = 30, filter: TaskFilter | None = None
    ) -> tuple[list[CloudTask], Pagination]:
        """List cloud download tasks.

        Args:
            page: Page number (1-based).
            page_size: Number of items per page.
            filter: Filter tasks by status.

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

    @abstractmethod
    def clear(self, filter: TaskFilter | None = None) -> None:
        """Clear cloud download tasks.

        Args:
            filter: Filter tasks to clear. If ``None``, clears all tasks.
        """

    @abstractmethod
    def retry(self, info_hash: str) -> None:
        """Retry a failed cloud download task.

        Args:
            info_hash: info_hash of the task to retry.
        """


class FileClient(ABC):
    """Abstract interface for file operations."""

    @abstractmethod
    def id(self, file_id: str) -> Directory | File:
        """Get info for a file or directory by its ID.

        Prefer this over other methods when the ID is already known,
        as it requires fewer requests than resolving by path.

        Args:
            file_id: The unique identifier of the file or directory.

        Returns:
            A Directory or File object.

        Raises:
            FileNotFoundError: If the path does not exist.
        """

    @abstractmethod
    def stat(self, path: str) -> Directory | File:
        """Get info for a file or directory at the given path.

        Args:
            path: Path to the file or directory.

        Returns:
            A Directory or File object.

        Raises:
            FileNotFoundError: If the path does not exist.
        """

    def list(
        self,
        path: str | Directory = "/",
        *,
        sort: SortField = SortField.FILENAME,
        sort_order: SortOrder = SortOrder.ASC,
    ) -> Sequence[Directory | File]:
        """Return a lazy collection of directory entries.

        Warning: Avoid fully loading all items if you don't know the total
        number of items, as this will trigger many API requests.

        Args:
            path: Directory path or :class:`Directory` object. ``"/"`` for root.
            sort: Sort field.
            sort_order: :attr:`SortOrder.ASC` or :attr:`SortOrder.DESC`.

        Returns:
            A :class:`~cli115.helpers.LazyCollection` of directory entries.

        Raises:
            FileNotFoundError: If the specified path does not exist.
            NotADirectoryError: If the specified path is not a directory.
        """

        if not isinstance(path, Directory):
            # eagerly resolve the path to validate its existence
            path = self.stat(path)
            if not path.is_directory:
                raise NotADirectoryError(f"not a directory: {path}")

        def fetch(
            page: int, page_size: int
        ) -> tuple[list[Directory | File], Pagination]:
            return self._list(
                path,
                sort=sort,
                sort_order=sort_order,
                limit=page_size,
                offset=(page - 1) * page_size,
            )

        return LazyCollection(fetch, page_size=DEFAULT_PAGE_SIZE)

    @abstractmethod
    def _list(
        self,
        path: str | Directory = "/",
        *,
        sort: SortField = SortField.FILENAME,
        sort_order: SortOrder = SortOrder.ASC,
        limit: int = DEFAULT_PAGE_SIZE,
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

    def find(
        self,
        query: str,
        *,
        path: str | Directory | None = None,
    ) -> Sequence[Directory | File]:
        """Return a lazy collection of search results.

        Warning: Avoid fully loading all items if you don't know the total
        number of items, as this will trigger many API requests.

        Args:
            query: Search string.
            path: Directory to search within. ``None`` for a global search.

        Returns:
            A :class:`~cli115.helpers.LazyPathCollection` of matching entries.

        Raises:
            FileNotFoundError: If a non-global search is performed and the
                specified path does not exist.
        """

        def fetch(
            page: int, page_size: int
        ) -> tuple[list[Directory | File], Pagination]:
            return self._find(
                query,
                path=path,
                limit=page_size,
                offset=(page - 1) * page_size,
            )

        return LazyPathCollection(fetch, page_size=DEFAULT_PAGE_SIZE)

    @abstractmethod
    def _find(
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
    def create_directory(self, path: str, *, parents: bool = False) -> Directory:
        """Create a new directory.

        Args:
            path: Absolute path of the directory to create
                  (e.g. ``"/photos/vacation"``).
            parents: If ``True``, create any missing parent directories
                     automatically (like ``mkdir -p``). If ``False`` (default),
                     raise :exc:`FileNotFoundError` when the parent does not exist.

        Returns:
            The created Directory.

        Raises:
            FileExistsError: A directory already exists at the given path if parents
                 is False
            FileNotFoundError: If a parent dir does not exist and ``parents`` is
                ``False``.

        Note:
            The server does not prevent duplicate names.  If a sibling file with the
            same name already exists, a second entry sharing that name will be created.
            Verify the new name is unique before calling this method.
        """

    @abstractmethod
    def delete(self, path: str | FileSystemEntry, *, recursive: bool = False) -> None:
        """Delete a file or directory (moves to recycle bin).

        Args:
            path: Path to the item to delete.
            recursive: If ``True``, delete the item even when it is a
                       non-empty directory. If ``False`` (default), raise
                       :exc:`FileExistsError` when the directory contains children.

        Raises:
            FileNotFoundError: If the path does not exist.
            FileExistsError: If ``recursive`` is ``False`` and the directory is not empty.
        """

    @abstractmethod
    def batch_delete(
        self, *paths: str | FileSystemEntry, recursive: bool = False
    ) -> None:
        """Delete multiple files/directories.

        Args:
            paths: Paths of items to delete.
            recursive: If ``True``, delete the items even when they are
                       non-empty directories. If ``False`` (default), raise
                       :exc:`FileExistsError` when any directory contains children.

        Raises:
            FileNotFoundError: If any path does not exist.
            FileExistsError: If ``recursive`` is ``False`` and a directory is not empty.
        """

    @abstractmethod
    def rename(self, path: str | FileSystemEntry, name: str) -> None:
        """Rename a file or directory.

        Args:
            path: Path to the item to rename.
            name: New name.

        Raises:
            FileNotFoundError: If the path does not exist.

        Note:
            The server does not prevent duplicate names.  If a sibling with
            ``name`` already exists, a second entry sharing that name will be
            created.  Verify the new name is unique before calling this method.
        """

    @abstractmethod
    def move(self, src: str | FileSystemEntry, dest_dir: str | Directory) -> None:
        """Move a file or directory to a destination folder.

        Args:
            src: Path to the item to move.
            dest_dir: Destination directory path or :class:`Directory` object.

        Raises:
            FileNotFoundError: If the source or destination does not exist.

        Note:
            The server does not prevent duplicate names.  If ``dest_dir``
            already contains an item with the same name as ``src``, a second
            entry sharing that name will be created.  Verify the name is
            unique in the destination before calling this method.
        """

    @abstractmethod
    def batch_move(
        self, *srcs: str | FileSystemEntry, dest_dir: str | Directory
    ) -> None:
        """Move multiple items to a destination folder.

        Args:
            srcs: Paths of items to move.
            dest_dir: Destination directory path or :class:`Directory` object.

        Raises:
            FileNotFoundError: If any source or the destination does not exist.

        Note:
            The server does not prevent duplicate names.  If ``dest_dir``
            already contains an item with the same name as any source, a
            second entry sharing that name will be created.  Verify all names
            are unique in the destination before calling this method.
        """

    @abstractmethod
    def copy(self, src: str | FileSystemEntry, dest_dir: str | Directory) -> None:
        """Copy a file or directory to a destination folder.

        Args:
            src: Path to the item to copy.
            dest_dir: Destination directory path or :class:`Directory` object.

        Raises:
            FileNotFoundError: If the source or destination does not exist.

        Note:
            The server does not prevent duplicate names.  If ``dest_dir``
            already contains an item with the same name as ``src``, a second
            entry sharing that name will be created.  Verify the name is
            unique in the destination before calling this method.
        """

    @abstractmethod
    def batch_copy(
        self, *srcs: str | FileSystemEntry, dest_dir: str | Directory
    ) -> None:
        """Copy multiple items to a destination folder.

        Args:
            srcs: Paths of items to copy.
            dest_dir: Destination directory path or :class:`Directory` object.

        Raises:
            FileNotFoundError: If any source or the destination does not exist.

        Note:
            The server does not prevent duplicate names.  If ``dest_dir``
            already contains an item with the same name as any source, a
            second entry sharing that name will be created.  Verify all names
            are unique in the destination before calling this method.
        """

    def upload(
        self,
        path: str,
        file: str | PathLike[str] | BinaryIO,
        *,
        instant_only: int | None = None,
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
            instant_only: If set to a byte threshold (e.g. ``100 * 1024 * 1024``
                  for 100 MB), files at or above that size will use instant
                  upload only — the upload fails with
                  :class:`~cli115.exceptions.InstantUploadNotAvailableError`
                  if the server does not have a matching copy.  Values below
                  :data:`MIN_INSTANT_UPLOAD_SIZE` are ignored.
            progress_callback: Optional callable invoked periodically
                  with a :class:`Progress` instance.

        Returns:
            The uploaded File entry.

        Raises:
            FileExistsError: If a file already exists at ``path``.
            FileNotFoundError: If the parent directory does not exist.
            InstantUploadNotAvailableError: When the file meets the
                ``instant_only`` threshold and the server does not have a
                matching copy of the file.
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
        instant_only: int | None = None,
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
    def url(self, path: str | File, *, user_agent: str | None = None) -> DownloadUrl:
        """Get download information for an existing file.

        Args:
            path: Path to the file or a :class:`File` object.
            user_agent: Custom User-Agent string for the download request.
                If ``None``, uses :data:`DEFAULT_USER_AGENT`.

        Returns:
            A DownloadUrl object with url, user-agent, cookies, and file metadata.

        Raises:
            FileNotFoundError: If the path does not exist.
            IsADirectoryError: If ``path`` points to a directory.
        """

    def open(self, path: str | File, *, user_agent: str | None = None) -> RemoteFile:
        """Get a lazy file-like object for a remote file.

        The returned :class:`RemoteFile` supports ``read``, ``seek`` and
        ``tell``.  Content is only downloaded when :meth:`~RemoteFile.read`
        is called, and Range headers are used for partial reads.

        Args:
            path: Path to the file or a :class:`File` object.
            user_agent: Custom User-Agent string for the download request.
                If ``None``, uses :data:`DEFAULT_USER_AGENT`.

        Returns:
            A :class:`RemoteFile` wrapping the download URL.

        Raises:
            FileNotFoundError: If the path does not exist.
            IsADirectoryError: If ``path`` points to a directory.
        """
        info = self.url(path, user_agent=user_agent)
        return RemoteFile(info)


class RemoteFile:
    """A file-like object that lazily reads content from a remote URL.

    By default, Range headers are used for partial reads.  Call
    :meth:`set_stream` to switch to httpx streaming mode, which reads the
    file sequentially via :meth:`httpx.Response.iter_bytes` without using
    Range headers.
    """

    def __init__(self, info: DownloadUrl) -> None:
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
