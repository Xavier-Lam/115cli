"""Client interface definitions for cli115."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta
from enum import Enum
from os import PathLike
from typing import BinaryIO, Callable


DEFAULT_PAGE_SIZE = 115  # Default number of items to return in list operations
MAX_PAGE_SIZE = 1150  # 1150 is the maximum page size allowed by the API
MIN_INSTANT_UPLOAD_SIZE = 2 * 1024 * 1024  # Minimum file size for instant upload
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0"
)


class SortField(str, Enum):
    """Field to sort file listings by."""

    FILENAME = "file_name"
    SIZE = "file_size"
    TYPE = "file_type"
    MODIFIED_TIME = "user_utime"
    CREATED_TIME = "user_ptime"
    OPEN_TIME = "user_otime"


class SortOrder(int, Enum):
    """Sort direction for file listings."""

    ASC = 1
    DESC = 0


@dataclass(frozen=True)
class Pagination:
    """Pagination metadata returned from list operations."""

    total: int
    offset: int
    limit: int


@dataclass(frozen=True)
class Progress:
    """Upload progress information passed to progress callbacks.

    Attributes:
        total_bytes: Total size of the file being uploaded in bytes.
        completed_bytes: Number of bytes uploaded so far.
        duration: Time elapsed since the upload started.
    """

    total_bytes: int
    completed_bytes: int
    duration: timedelta


@dataclass
class FileSystemEntry:
    """Base class for file system entries (files and directories).

    Attributes:
        id: Unique identifier of the entry.
        parent_id: Identifier of the parent directory.
        name: Name of the entry.
        path: Absolute path of the entry. Set by methods that resolve by path;
            ``None`` when only the ID is known (e.g. returned by ``id()``).
        pickcode: Pickcode used for downloading.
        created_time: When the entry was created.
        modified_time: When the entry was last modified.
        open_time: When the entry was last opened.
        labels: List of user-assigned label names.
    """

    id: str
    parent_id: str
    name: str
    path: str | None
    pickcode: str
    created_time: datetime | None
    modified_time: datetime | None
    open_time: datetime | None
    labels: list[str] = field(default_factory=list)

    @property
    def is_directory(self) -> bool:
        """Whether this entry is a directory."""
        raise NotImplementedError


@dataclass
class Directory(FileSystemEntry):
    """A directory in the 115 netdisk.

    Attributes:
        file_count: Number of items inside this directory.
    """

    file_count: int = 0

    @property
    def is_directory(self) -> bool:
        """Whether this entry is a directory."""
        return True


@dataclass
class File(FileSystemEntry):
    """A file in the 115 netdisk.

    Attributes:
        size: File size in bytes.
        sha1: SHA-1 hash of the file content.
        file_type: File type / icon identifier (e.g. ``"mp4"``, ``"doc"``).
        starred: Whether the file is starred.
    """

    size: int = 0
    sha1: str = ""
    file_type: str = ""
    starred: bool = False

    @property
    def is_directory(self) -> bool:
        """Whether this entry is a directory."""
        return False


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
        if self._file_client is None:
            return None
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
    cls = type(f"Lazy{cls.__name__}", (LazyPathMixin, cls), {})
    attrs = {f.name: getattr(item, f.name) for f in fields(item)}
    rv = cls(**attrs)
    rv._file_client = client
    return rv


class TaskStatus(int, Enum):
    """Status of a cloud download task."""

    FAILED = -1
    WAITING = 0
    DOWNLOADING = 1
    COMPLETED = 2


@dataclass(frozen=True)
class DownloadQuota:
    """Cloud download quota information.

    Attributes:
        quota: Remaining task quota.
        total: Total task quota.
    """

    quota: int
    total: int


@dataclass
class CloudTask:
    """A cloud download (offline) task.

    Attributes:
        info_hash: Task identifier hash.
        name: Task / file name.
        size: Total size in bytes.
        status: Task status.
        percent_done: Download progress (0–100).
        url: Source URL / magnet link.
        file_id: 115 file ID (populated when complete).
        pick_code: Pickcode (populated when complete).
        folder_id: Target folder ID.
        add_time: When the task was created.
    """

    info_hash: str
    name: str
    size: int
    status: TaskStatus
    percent_done: float
    url: str
    file_id: str = ""
    pick_code: str = ""
    folder_id: str = ""
    add_time: datetime | None = None


@dataclass(frozen=True)
class DownloadInfo:
    """Download information for an existing file.

    Attributes:
        url: Direct download URL.
        file_name: Name of the file.
        file_size: Size of the file in bytes.
        sha1: SHA-1 hex digest (upper-case) of the file content.
        user_agent: User-Agent header required for the download request.
        referer: Referer header required for the download request.
        cookies: Cookie header value (e.g. ``"UID=a; CID=b; ..."``).
    """

    url: str
    file_name: str
    file_size: int
    sha1: str
    user_agent: str
    referer: str
    cookies: str


@dataclass(frozen=True)
class AccountInfo:
    """Account information for the authenticated user.

    Attributes:
        user_name: Display name of the user.
        user_id: Numeric user ID.
        vip: Whether the user currently has VIP status.
        expire: VIP expiry datetime, or ``None`` if not available.
    """

    user_name: str
    user_id: int
    vip: bool
    expire: datetime | None


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

    @abstractmethod
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


class AccountClient(ABC):
    """Abstract interface for account operations."""

    @abstractmethod
    def info(self) -> AccountInfo:
        """Get account information for the authenticated user.

        Returns:
            An AccountInfo with user name, user ID, VIP status and expiry.
        """
