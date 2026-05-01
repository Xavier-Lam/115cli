"""Data model classes for cli115."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import BinaryIO

from blinker import Signal

# region Enums


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


class TaskStatus(int, Enum):
    """Status of a cloud download task."""

    FAILED = -1
    WAITING = 0
    DOWNLOADING = 1
    COMPLETED = 2


class TaskFilter(str, Enum):
    """Filter type for listing or clearing cloud download tasks."""

    COMPLETED = "completed"
    FAILED = "failed"
    RUNNING = "running"


# endregion
# region File System Models


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


# endregion
# region Data Models


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
class DownloadUrl:
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
class DownloadQuota:
    """Cloud download quota information.

    Attributes:
        quota: Remaining task quota.
        total: Total task quota.
    """

    quota: int
    total: int


@dataclass(frozen=True)
class Pagination:
    """Pagination metadata returned from list operations."""

    total: int
    offset: int
    limit: int


class Progress:
    """Tracks download or upload progress for a single file.

    Attributes:
        total_bytes: Total size of the file being uploaded in bytes.
        completed_bytes: Number of bytes uploaded so far.
        duration: Time elapsed since the upload started.
        on_change: Signal emitted whenever progress is updated.
    """

    _start_time: datetime | None = None
    _end_time: datetime | None = None

    def __init__(self, total_bytes: int) -> None:
        self._total_bytes: int = total_bytes
        self._completed_bytes: int = 0
        self.on_change: Signal = Signal()

    @property
    def total_bytes(self) -> int:
        return self._total_bytes

    @property
    def completed_bytes(self) -> int:
        return self._completed_bytes

    @property
    def duration(self) -> timedelta:
        if self._start_time is None:
            return timedelta(0)
        if self._end_time is not None:
            return self._end_time - self._start_time
        return datetime.now() - self._start_time

    def is_started(self) -> bool:
        return self._start_time is not None

    def is_completed(self) -> bool:
        return self._completed_bytes >= self._total_bytes

    def is_failed(self) -> bool:
        return self._end_time is not None and not self.is_completed()

    def start(self) -> None:
        self._start_time = datetime.now()

    def update(self, delta: int) -> None:
        new = self._completed_bytes + delta
        if new < self._total_bytes:
            old = self._completed_bytes
            self._completed_bytes += delta
            self.on_change.send(
                self,
                delta=delta,
                new=new,
                old=old,
                completed=False,
            )
        else:
            self.complete()

    def complete(self) -> None:
        old = self._completed_bytes
        delta = self._total_bytes - old
        self._completed_bytes = self._total_bytes
        self._end_time = datetime.now()
        self.on_change.send(
            self,
            delta=delta,
            new=self._total_bytes,
            old=old,
            completed=True,
        )

    def failed(self) -> None:
        self._end_time = datetime.now()

    @contextmanager
    def patch_file(self, file: BinaryIO):
        original_read = file.read

        def patched_read(size=-1) -> bytes:
            chunk = original_read(size)
            self.update(len(chunk))
            return chunk

        file.read = patched_read
        try:
            yield
        finally:
            file.read = original_read

    def __enter__(self) -> Progress:
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is None:
            self.complete()
        else:
            self.failed()


class UploadStatus:
    def __init__(self) -> None:
        self._is_instant_uploaded: bool | None = None
        self._instant_upload_error: Exception | None = None
        self._is_completed: bool = False
        self.on_message: Signal = Signal()
        self.on_upload: Signal = Signal()
        self.on_complete: Signal = Signal()

    @property
    def is_instant_uploaded(self) -> bool | None:
        """Whether the file has been instantly uploaded. ``None`` if not
        determined yet (e.g. upload not started).
        """
        return self._is_instant_uploaded

    @is_instant_uploaded.setter
    def is_instant_uploaded(self, value: bool | None) -> None:
        self._is_instant_uploaded = value
        if value:
            self._complete()
            self.set_message("instant upload successful")

    @property
    def instant_upload_error(self) -> Exception | None:
        """The error encountered during instant upload, if any."""
        return self._instant_upload_error

    @instant_upload_error.setter
    def instant_upload_error(self, value: Exception | None) -> None:
        self._instant_upload_error = value
        self.set_message(f"instant upload failed: {value}")

    def set_message(self, message: str) -> None:
        self.on_message.send(self, message=message)

    @contextmanager
    def start_upload(self, file_size: int):
        progress = Progress(file_size)
        self.on_upload.send(self, progress=progress)
        progress.on_change.connect(
            lambda sender, completed, **_: completed and self._complete(),
            weak=False,
        )
        self.set_message("uploading...")
        yield progress

    @property
    def is_completed(self) -> bool:
        return self._is_completed

    def _complete(self):
        if not self.is_completed:
            self._is_completed = True
            self.on_complete.send(self)


@dataclass(frozen=True)
class Usage:
    """Disk storage information.

    Attributes:
        total: Total storage capacity in bytes.
        used: Used storage in bytes.
        remaining: Remaining (free) storage in bytes.
    """

    total: int
    used: int
    remaining: int


# endregion
