from __future__ import annotations

import hashlib
import json
import os
from typing import BinaryIO

import httpx
from p115cipher import ecdh_aes_decrypt, make_upload_payload

from cli115.client.base import (
    DEFAULT_PAGE_SIZE,
    FileClient as BaseFileClient,
    MAX_PAGE_SIZE,
    MIN_INSTANT_UPLOAD_SIZE,
    RemoteFile,
)
from cli115.client.lazy import new_lazy_cls
from cli115.client.models import (
    Directory,
    DownloadUrl,
    File,
    FileSystemEntry,
    Pagination,
    SortField,
    SortOrder,
    UploadStatus,
)
from cli115.client.utils import parse_item, parse_ts
from cli115.exceptions import InstantUploadNotAvailableError
from cli115.helpers import normalize_path, sha1_file, join_path
from .base import (
    APP_USER_AGENT,
    APP_VERSION,
    BaseClient,
    DEFAULT_USER_AGENT,
    Endpoint,
)


class FileClient(BaseFileClient, BaseClient):

    # -- public API --

    def id(self, file_id: str) -> Directory | File:
        resp = self._api.get(
            Endpoint.WEBAPI + "/files/get_info",
            params={"file_id": file_id},
        )
        data = resp.json()["data"]
        if not data:
            raise FileNotFoundError(f"file id not found: {file_id}")
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
            dir_id = self._resolve_dir_id(path)
        # both /files/order and /files need to be called to get correct
        # sorting results, otherwise the sorting parameters are ignored
        self._api.post(
            Endpoint.WEBAPI + "/files/order",
            data={
                "file_id": dir_id,
                "user_order": sort.value,
                "user_asc": sort_order.value,
                # mix files and directories together in the listing, instead of
                # always listing directories first
                "fc_mix": 1,
            },
        )
        resp = self._api.get(
            Endpoint.WEBAPI + "/files",
            params={
                "aid": 1,  # normal files
                "cid": dir_id,
                "offset": offset,
                "limit": min(limit, MAX_PAGE_SIZE),
                "show_dir": 1,
                "natsort": 1,
                "o": sort.value,
                "asc": sort_order.value,
                "fc_mix": 1,
            },
        ).json()

        items: list[Directory | File] = []
        for raw in resp.get("data", []):
            item = parse_item(raw)
            if path is not None:
                item.path = join_path(path, item.name)
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
            "aid": 1,  # normal files
            "cid": "0",
            "show_dir": 1,
        }
        if path is not None:
            payload["cid"] = self._resolve_dir_id(path)

        resp = self._api.get(
            Endpoint.WEBAPI + "/files/search",
            params=payload,
        ).json()

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
            pid = self._resolve_dir_id(dirname)
        except FileNotFoundError:
            if not parents:
                raise
            parent_dir = self.create_directory(dirname, parents=True)
            pid = parent_dir.id

        try:
            resp = self._api.post(
                Endpoint.WEBAPI + "/files/add",
                data={"cname": name, "pid": pid},
            ).json()
        except FileExistsError:
            if parents:
                return self.stat(path)  # directory already exists, return it
            raise
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
        entry = self.stat(path)
        if not recursive and entry.is_directory:
            items = self.list(path)
            if len(items) > 0:
                raise FileExistsError(f"directory is not empty: {path}")
        self._api.post(
            Endpoint.WEBAPI + "/rb/delete",
            data={"fid": entry.id},
        )

    def batch_delete(
        self, *paths: str | FileSystemEntry, recursive: bool = False
    ) -> None:
        if recursive:
            raise NotImplementedError("recursive batch delete is not yet supported")
        ids = [self._resolve_id(p) for p in paths]
        self._api.post(
            Endpoint.WEBAPI + "/rb/delete",
            data={f"fid[{i}]": id_ for i, id_ in enumerate(ids)},
        )

    def rename(self, path: str | FileSystemEntry, name: str) -> None:
        file_id = self._resolve_id(path)
        self._api.post(
            Endpoint.WEBAPI + "/files/batch_rename",
            data={f"files_new_name[{file_id}]": name},
        )

    def move(self, src: str | FileSystemEntry, dest_dir: str | Directory) -> None:
        self.batch_move(src, dest_dir=dest_dir)

    def batch_move(
        self, *srcs: str | FileSystemEntry, dest_dir: str | Directory
    ) -> None:
        src_ids = [self._resolve_id(s) for s in srcs]
        dest_id = self._resolve_dir_id(dest_dir)
        self._api.post(
            Endpoint.WEBAPI + "/files/move",
            data={f"fid[{i}]": id_ for i, id_ in enumerate(src_ids)} | {"pid": dest_id},
        )

    def copy(self, src: str | FileSystemEntry, dest_dir: str | Directory) -> None:
        self.batch_copy(src, dest_dir=dest_dir)

    def batch_copy(
        self, *srcs: str | FileSystemEntry, dest_dir: str | Directory
    ) -> None:
        src_ids = [self._resolve_id(s) for s in srcs]
        dest_id = self._resolve_dir_id(dest_dir)
        self._api.post(
            Endpoint.WEBAPI + "/files/copy",
            data={f"fid[{i}]": id_ for i, id_ in enumerate(src_ids)} | {"pid": dest_id},
        )

    def _upload(
        self,
        path: str,
        file: BinaryIO,
        *,
        instant_only: int | None = None,
        status: UploadStatus | None = None,
    ) -> File:
        if not status:
            status = UploadStatus()
        path = normalize_path(path)

        # raise an error if the file already exists
        status.set_message("checking for existing file...")
        try:
            self.stat(path)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError(f"remote path '{path}' already exists")

        parent_path = os.path.dirname(path)
        filename = os.path.basename(path)
        dir_id = self._resolve_dir_id(parent_path)

        status.set_message("calculating file hash...")
        sha1, file_size = sha1_file(file)
        status.set_message(f"file sha1 calculated: {sha1}, size: {file_size} bytes")

        # Only attempt instant upload when the file meets the minimum size.
        if file_size >= MIN_INSTANT_UPLOAD_SIZE:
            status.set_message("attempting instant upload")
            force_instant = instant_only is not None and file_size >= instant_only
            try:
                self._try_instant_upload(
                    file=file,
                    filename=filename,
                    file_size=file_size,
                    sha1=sha1,
                    dir_id=dir_id,
                )
                status.is_instant_uploaded = True
                return self.stat(path)
            except Exception as exc:
                status.instant_upload_error = exc
                if force_instant:
                    raise
            file.seek(0)

        if isinstance(file, RemoteFile):
            file.set_stream(True)  # use streaming upload for RemoteFile

        status.is_instant_uploaded = False
        with status.start_upload(file_size) as progress, progress.patch_file(file):
            resp = self._upload_file_sample(file, pid=dir_id, filename=filename)
        data = resp["data"]

        status.set_message("upload completed")

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
    ) -> None:
        """Attempt instant upload.  Return `True` on success, `False` if the
        server does not have this file and a regular upload is required."""

        def read_range(range_str: str) -> bytes:
            # sign_check format is "start-end" (inclusive), like HTTP Range.
            start, end = [int(x) for x in range_str.split("-")]
            file.seek(start)
            return file.read(end - start + 1)

        upload_info = self._api.get(Endpoint.PROAPI + "/app/uploadinfo").json()

        payload = {
            "filename": filename,
            "fileid": sha1.upper(),
            "filesize": file_size,
            "target": f"U_1_{dir_id}",
            "appid": 0,
            "sign_key": "",
            "sign_val": "",
            "topupload": "true",
            "appversion": APP_VERSION,
            "userid": upload_info["user_id"],
            "userkey": upload_info["userkey"],
        }
        resp = self._post_upload_init(payload)
        status = int(resp["status"])
        if status == 7:
            sign_check = str(resp.get("sign_check", ""))
            payload["sign_key"] = str(resp.get("sign_key", ""))
            payload["sign_val"] = (
                hashlib.sha1(read_range(sign_check)).hexdigest().upper()
            )
            resp = self._post_upload_init(payload)
            status = int(resp["status"])

        if status != 2:
            raise InstantUploadNotAvailableError(
                "instant upload is not available (file not found on server)"
            )

    def _post_upload_init(self, payload: dict) -> dict:
        resp = self._api.post(
            Endpoint.UPLB + "/4.0/initupload.php",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": APP_USER_AGENT,
            },
            **make_upload_payload(payload.copy()),
        )
        return json.loads(ecdh_aes_decrypt(resp.content, decompress=True))

    def _upload_file_sample(self, file: BinaryIO, *, pid: str, filename: str) -> dict:
        sample_info = self._api.post(
            Endpoint.UPLB + "/3.0/sampleinitupload.php",
            data={"filename": filename, "target": f"U_1_{pid}"},
        ).json()
        resp = httpx.post(
            sample_info["host"],
            data={
                "name": filename,
                "key": sample_info["object"],
                "policy": sample_info["policy"],
                "OSSAccessKeyId": sample_info["accessid"],
                "success_action_status": "200",
                "callback": sample_info["callback"],
                "signature": sample_info["signature"],
            },
            files={"file": (filename, file)},
            timeout=None,
        )
        data = resp.json()
        data["oss_info"] = sample_info
        return data

    def url(self, path: str | File, *, user_agent: str | None = None) -> DownloadUrl:
        entry = self._resolve_entry(path)
        if entry.is_directory:
            raise IsADirectoryError("cannot get download info for a directory")

        ua = user_agent or self._api.headers.get("User-Agent", DEFAULT_USER_AGENT)
        resp = self._api.post_encrypted(
            Endpoint.PROAPI + "/app/chrome/downurl",
            data={"pickcode": entry.pickcode},
            headers={"User-Agent": ua},
        )
        raw_data = resp.json()
        download_url = ""
        for item in raw_data.values():
            if isinstance(item, dict) and item["pick_code"] == entry.pickcode:
                download_url = item["url"]["url"]
                break

        cookie_str = resp.request.headers["Cookie"]
        return DownloadUrl(
            url=download_url,
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
        for entry in self.list(dirname):
            if entry.name == name:
                return entry
        raise FileNotFoundError(f"entry not found: {path}")
