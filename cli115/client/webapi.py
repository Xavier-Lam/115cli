"""WebAPI client implementation backed by p115client."""

from __future__ import annotations

import os
import warnings
from datetime import datetime
from typing import BinaryIO, Callable

from cli115.api.web.p115client import check_response, P115Client
from cli115.auth import Auth
from cli115.client.base import (
    AccountClient,
    Client,
    DEFAULT_PAGE_SIZE,
    DownloadClient,
    FileClient,
    MAX_PAGE_SIZE,
    MIN_INSTANT_UPLOAD_SIZE,
    RemoteFile,
)
from cli115.client.lazy import new_lazy_cls
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
    TaskStatus,
)
from cli115.client.utils import parse_item, parse_ts
from cli115.exceptions import (
    AlreadyExistsError,
    InstantUploadNotAvailableError,
    NotFoundError,
)
from cli115.helpers import normalize_path, sha1_file


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0"
)


class WebAPIClient(Client):
    """High-level 115 client backed by the web API.

    Although it is named ``WebAPIClient``, a few of its APIs may come from
    other sources, such as the mobile phone app.
    """

    def __init__(self, auth: Auth):
        self._auth = auth
        self._api = P115Client(auth.get_cookies())
        self._account = WebAPIAccountClient(self)
        self._file = WebAPIFileClient(self)
        self._download = WebAPIDownloadClient(self)

    @property
    def account(self) -> AccountClient:
        return self._account

    @property
    def file(self) -> FileClient:
        return self._file

    @property
    def download(self) -> DownloadClient:
        return self._download

    def _resolve_dir_id(self, path: str | Directory) -> str:
        if isinstance(path, Directory):
            return path.id
        path = normalize_path(path)
        if path == "/":
            return "0"
        resp = self._api.fs_dir_getid({"path": path})
        resp = check_response(resp)
        dir_id = str(resp["id"])
        if dir_id == "0":
            # the api returns success with id=0 for non-existent paths
            raise NotFoundError("directory not found: %s" % path, errno=990002)
        return dir_id


class WebAPIAccountClient(AccountClient):

    def __init__(self, client: WebAPIClient):
        self._client = client

    def info(self) -> AccountInfo:
        resp = self._client._api.user_my()
        check_response(resp)
        data = resp.get("data", {})
        expire_ts = data.get("expire")
        expire = datetime.fromtimestamp(expire_ts) if expire_ts else None
        return AccountInfo(
            user_name=data.get("user_name", ""),
            user_id=int(data.get("user_id", 0)),
            vip=bool(data.get("vip", 0)),
            expire=expire,
        )


class WebAPIFileClient(FileClient):

    def __init__(self, client: WebAPIClient):
        self._client = client

    # -- public API --

    def id(self, file_id: str) -> Directory | File:
        resp = self._client._api.fs_file(file_id)
        resp = check_response(resp)
        data = resp.get("data", [])
        if not data:
            raise NotFoundError(f"Not found: {file_id}", errno=990002)
        item = parse_item(data[0])
        return new_lazy_cls(item, self)

    def stat(self, path: str) -> Directory | File:
        return self._resolve_entry(path)

    def _list(
        self,
        path: str | Directory = "/",
        *,
        sort: SortField = SortField.FILENAME,
        sort_order: SortOrder = SortOrder.ASC,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> tuple[list[Directory | File], Pagination]:
        if isinstance(path, Directory):
            dir_id = path.id
            path = path.path
        else:
            path = normalize_path(path)
            dir_id = self._client._resolve_dir_id(path)
        # both fs_order_set and fs_files need to be called to get correct
        # sorting results, otherwise the sorting parameters are ignored
        self._client._api.fs_order_set(
            {
                "file_id": dir_id,
                "user_order": sort.value,
                "user_asc": sort_order.value,
                "fc_mix": 1,
            }
        )
        resp = self._client._api.fs_files(
            {
                "cid": dir_id,
                "offset": offset,
                "limit": min(limit, MAX_PAGE_SIZE),
                "natsort": 1,
                "o": sort.value,
                "asc": sort_order.value,
                "fc_mix": 1,
            }
        )
        resp = check_response(resp)

        items: list[Directory | File] = []
        for raw in resp.get("data", []):
            item = parse_item(raw)
            if path is not None:
                item.path = f"{path.rstrip('/')}/{item.name}"
            items.append(item)

        pagination = Pagination(
            total=int(resp.get("count", 0)),
            offset=int(resp.get("offset", 0)),
            limit=int(resp.get("limit", limit)),
        )
        return items, pagination

    def _find(
        self,
        query: str,
        *,
        path: str | Directory | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> tuple[list[Directory | File], Pagination]:
        payload: dict = {
            "search_value": query,
            "offset": offset,
            "limit": min(limit, MAX_PAGE_SIZE),
        }
        if path is not None:
            payload["cid"] = self._client._resolve_dir_id(path)

        resp = self._client._api.fs_search(payload)
        resp = check_response(resp)

        items: list[Directory | File] = []
        for raw in resp.get("data", []):
            item = parse_item(raw)
            items.append(new_lazy_cls(item, self))

        pagination = Pagination(
            total=int(resp.get("count", 0)),
            offset=int(resp.get("offset", 0)),
            limit=int(resp.get("limit", limit)),
        )
        return items, pagination

    def create_directory(self, path: str, *, parents: bool = False) -> Directory:
        path = normalize_path(path)
        dirname = os.path.dirname(path)
        name = os.path.basename(path)

        try:
            pid = self._client._resolve_dir_id(dirname)
        except NotFoundError:
            if not parents:
                raise
            parent_dir = self.create_directory(dirname, parents=True)
            pid = parent_dir.id

        resp = self._client._api.fs_mkdir(name, pid=pid)
        resp = check_response(resp)
        return Directory(
            id=str(resp.get("cid") or resp.get("file_id", "")),
            parent_id=pid,
            name=resp.get("cname") or resp.get("file_name", ""),
            path=path,
            pickcode="",
            created_time=None,
            modified_time=None,
            open_time=None,
        )

    def delete(self, path: str | FileSystemEntry, *, recursive: bool = False) -> None:
        entry = self._resolve_entry(path)
        if not recursive and entry.is_directory:
            items = self.list(path)
            if len(items) > 0:
                raise AlreadyExistsError(f"Directory is not empty: {path}")
        resp = self._client._api.fs_delete(entry.id)
        check_response(resp)

    def batch_delete(
        self, *paths: str | FileSystemEntry, recursive: bool = False
    ) -> None:
        if recursive:
            raise NotImplementedError("recursive batch delete is not yet supported")
        ids = [self._resolve_id(p) for p in paths]
        resp = self._client._api.fs_delete(ids)
        check_response(resp)

    def rename(self, path: str | FileSystemEntry, name: str) -> None:
        file_id = self._resolve_id(path)
        resp = self._client._api.fs_rename((file_id, name))
        check_response(resp)

    def move(self, src: str | FileSystemEntry, dest_dir: str | Directory) -> None:
        src_id = self._resolve_id(src)
        dest_id = self._client._resolve_dir_id(dest_dir)
        resp = self._client._api.fs_move(src_id, pid=dest_id)
        check_response(resp)

    def batch_move(
        self, *srcs: str | FileSystemEntry, dest_dir: str | Directory
    ) -> None:
        src_ids = [self._resolve_id(s) for s in srcs]
        dest_id = self._client._resolve_dir_id(dest_dir)
        resp = self._client._api.fs_move(src_ids, pid=dest_id)
        check_response(resp)

    def copy(self, src: str | FileSystemEntry, dest_dir: str | Directory) -> None:
        src_id = self._resolve_id(src)
        dest_id = self._client._resolve_dir_id(dest_dir)
        resp = self._client._api.fs_copy(src_id, pid=dest_id)
        check_response(resp)

    def batch_copy(
        self, *srcs: str | FileSystemEntry, dest_dir: str | Directory
    ) -> None:
        src_ids = [self._resolve_id(s) for s in srcs]
        dest_id = self._client._resolve_dir_id(dest_dir)
        resp = self._client._api.fs_copy(src_ids, pid=dest_id)
        check_response(resp)

    def _upload(
        self,
        path: str,
        file: BinaryIO,
        *,
        instant_only: bool = False,
        progress_callback: Callable[[Progress], object] | None = None,
    ) -> File:
        path = normalize_path(path)

        # raise an error if the file already exists
        try:
            self.stat(path)
        except NotFoundError:
            pass
        else:
            raise AlreadyExistsError(f"File already exists: {path}", errno=0)

        parent_path = os.path.dirname(path)
        filename = os.path.basename(path)
        dir_id = self._client._resolve_dir_id(parent_path)

        sha1, file_size = sha1_file(file)

        # Only attempt instant upload when the file meets the minimum size.
        if file_size >= MIN_INSTANT_UPLOAD_SIZE:
            try:
                success = self._try_instant_upload(
                    file=file,
                    filename=filename,
                    file_size=file_size,
                    sha1=sha1,
                    dir_id=dir_id,
                    path=path,
                )
            except Exception as exc:
                if instant_only:
                    raise
                warnings.warn(
                    f"Instant upload failed ({exc}); falling back to " "normal upload",
                    stacklevel=2,
                )
            else:
                if success:
                    return self.stat(path)
                if instant_only:
                    raise InstantUploadNotAvailableError(
                        "Instant upload is not available for this file "
                        "(file not found on server)",
                        errno=0,
                    )
            file.seek(0)

        if isinstance(file, RemoteFile):
            file.set_stream(True)  # use streaming upload for RemoteFile

        resp = self._client._api.upload_file_sample(
            file,
            pid=dir_id,
            filename=filename,
        )
        resp = check_response(resp)
        data = resp.get("data", {})

        return File(
            id=str(data.get("file_id", "")),
            parent_id=str(dir_id),
            name=data.get("file_name", ""),
            path=path,
            pickcode=data.get("pick_code", ""),
            created_time=parse_ts(data.get("file_ptime")),
            modified_time=None,
            open_time=None,
            sha1=data.get("sha1", ""),
            size=int(data.get("file_size", 0)),
        )

    def _try_instant_upload(
        self,
        *,
        file: BinaryIO,
        filename: str,
        file_size: int,
        sha1: str,
        dir_id: str,
        path: str,
    ) -> bool:
        """Attempt instant upload.  Return `True` on success, `False` if the
        server does not have this file and a regular upload is required."""

        def read_range(range_str: str) -> bytes:
            # sign_check format is "start-end" (inclusive), like HTTP Range.
            start, end = [int(x) for x in range_str.split("-")]
            file.seek(start)
            return file.read(end - start + 1)

        resp = self._client._api.upload_file_init(
            filename=filename,
            filesize=file_size,
            filesha1=sha1,
            read_range_bytes_or_hash=(read_range if file_size >= 1024 * 1024 else None),
            pid=dir_id,
        )

        return bool(resp.get("reuse"))

    def url(self, path: str | File, *, user_agent: str | None = None) -> DownloadUrl:
        entry = self._resolve_entry(path)
        if entry.is_directory:
            raise ValueError("Cannot get download info for a directory")
        assert isinstance(entry, File)

        ua = user_agent or DEFAULT_USER_AGENT
        p115url = self._client._api.download_url(entry.pickcode, user_agent=ua)
        cookie_str = "; ".join(
            f"{k}={m.value}" for k, m in self._client._api.cookies.items()
        )
        return DownloadUrl(
            url=str(p115url),
            file_name=entry.name,
            file_size=entry.size,
            sha1=entry.sha1,
            user_agent=ua,
            referer="https://115.com/",
            cookies=cookie_str,
        )

    # -- path resolution helpers --

    def _resolve_id(self, path: str | FileSystemEntry) -> str:
        entry = self._resolve_entry(path)
        return entry.id

    def _resolve_entry(self, path: str | FileSystemEntry) -> FileSystemEntry:
        if isinstance(path, FileSystemEntry):
            return path
        path = normalize_path(path)
        if path == "/":
            return Directory(
                id="0",
                parent_id="",
                path="/",
                name="/",
                pickcode="",
                created_time=None,
                modified_time=None,
                open_time=None,
                file_count=0,
            )
        dirname = os.path.dirname(path)
        name = os.path.basename(path)
        pid = self._client._resolve_dir_id(dirname)
        offset = 0
        while True:
            resp = self._client._api.fs_files(
                {
                    "cid": pid,
                    "aid": 1,
                    "offset": offset,
                    "limit": MAX_PAGE_SIZE,
                    "show_dir": 1,
                }
            )
            resp = check_response(resp)
            data = resp.get("data", [])
            for item in data:
                if item.get("n") == name:
                    rv = parse_item(item)
                    rv.path = path
                    return rv
            total = int(resp.get("count", 0))
            offset += len(data)
            if offset >= total or not data:
                break
        raise NotFoundError(f"Not found: {path}", errno=990002)


class WebAPIDownloadClient(DownloadClient):

    def __init__(self, client: WebAPIClient):
        self._client = client

    def quota(self) -> DownloadQuota:
        resp = self._client._api.offline_quota_info()
        resp = check_response(resp)
        return DownloadQuota(
            quota=int(resp.get("quota", 0)),
            total=int(resp.get("total", 0)),
        )

    def _list(
        self, page: int = 1, page_size: int = 30
    ) -> tuple[list[CloudTask], Pagination]:
        resp = self._client._api.offline_list({"page": page})
        resp = check_response(resp)
        tasks = [self._parse_task(t) for t in resp.get("tasks", [])]
        page_size = int(resp.get("page_row", resp.get("page_size", page_size)))
        pagination = Pagination(
            total=int(resp.get("count", 0)),
            offset=(int(resp.get("page", 1)) - 1) * page_size,
            limit=page_size,
        )
        return tasks, pagination

    def add_url(
        self, url: str, *, dest_dir: str | Directory | None = None
    ) -> CloudTask:
        payload: dict = {"url": url}
        if dest_dir is not None:
            payload["wp_path_id"] = self._client._resolve_dir_id(dest_dir)
        resp = self._client._api.offline_add_url(payload)
        resp = check_response(resp)
        data = resp.get("data", {})
        info_hash = data.get("info_hash", "")
        return self._find_task(info_hash)

    def add_urls(
        self, *urls: str, dest_dir: str | Directory | None = None
    ) -> list[CloudTask]:
        if dest_dir is not None:
            wp_path_id = self._client._resolve_dir_id(dest_dir)
            resp = self._client._api.offline_add_urls(
                list(urls), {"wp_path_id": wp_path_id}
            )
        else:
            resp = self._client._api.offline_add_urls(list(urls))
        resp = check_response(resp)
        data = resp.get("data", {})
        result = data.get("result", [])
        hashes = [r.get("info_hash", "") for r in result]
        tasks_map = self._fetch_tasks_map()
        return [tasks_map[h] for h in hashes if h in tasks_map]

    def delete(self, *task_hashes: str) -> None:
        resp = self._client._api.offline_remove(list(task_hashes))
        check_response(resp)

    def _find_task(self, info_hash: str) -> CloudTask:
        """Find a task by info_hash in the task list."""
        tasks_map = self._fetch_tasks_map()
        if info_hash in tasks_map:
            return tasks_map[info_hash]
        # Return a minimal CloudTask if not found in list
        return CloudTask(
            info_hash=info_hash,
            name="",
            size=0,
            status=TaskStatus.WAITING,
            percent_done=0,
            url="",
        )

    def _fetch_tasks_map(self) -> dict[str, CloudTask]:
        """Fetch the first page of tasks and return a dict keyed by info_hash."""
        tasks, _ = self._list(page=1)
        return {t.info_hash: t for t in tasks}

    def _parse_task(self, task: dict) -> CloudTask:
        """Convert a raw task dict from the API into a CloudTask."""
        return CloudTask(
            info_hash=task.get("info_hash", ""),
            name=task.get("name", ""),
            size=int(task.get("size", 0)),
            status=TaskStatus(int(task.get("status", 0))),
            percent_done=float(task.get("percentDone", 0)),
            url=task.get("url", ""),
            file_id=str(task.get("file_id", "") or ""),
            pick_code=task.get("pick_code", "") or "",
            folder_id=str(task.get("wp_path_id", "") or ""),
            add_time=parse_ts(task.get("add_time")),
        )
