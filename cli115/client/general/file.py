from __future__ import annotations

import base64
from email.utils import formatdate
import hashlib
import hmac
import json
import os
from typing import BinaryIO
from urllib.parse import urlsplit, urlunsplit
import xml.etree.ElementTree as ET

import httpcore
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
from cli115.client.utils import create_multipart_request, parse_item, parse_ts
from cli115.exceptions import InstantUploadNotAvailableError
from cli115.helpers import normalize_path, sha1_file, join_path
from .base import (
    APP_USER_AGENT,
    APP_VERSION,
    BaseClient,
    DEFAULT_USER_AGENT,
    Endpoint,
)

# 16 MB per chunk; also used as the threshold for switching to multipart upload
MULTIPART_UPLOAD_PART_SIZE = 16 * 1024 * 1024


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
        # The initupload.php response (status=1) is preserved so a subsequent
        # multipart upload can reuse the bucket/object/callback metadata.
        init_data: dict | None = None
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
                if isinstance(exc, InstantUploadNotAvailableError):
                    init_data = exc.response_data
            file.seek(0)

        if isinstance(file, RemoteFile):
            file.set_stream(True)

        status.is_instant_uploaded = False
        with status.start_upload(file_size) as progress, progress.patch_file(file):
            if init_data is None:
                resp = self._upload_file_sample(file, pid=dir_id, filename=filename)
            else:
                resp = self._do_multipart_upload(
                    file,
                    bucket=init_data["bucket"],
                    object=init_data["object"],
                    callback=init_data["callback"],
                )
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
                "instant upload is not available (file not found on server)",
                response_data=resp,
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

        fields = {
            "name": filename,
            "key": sample_info["object"],
            "policy": sample_info["policy"],
            "OSSAccessKeyId": sample_info["accessid"],
            "success_action_status": "200",
            "callback": sample_info["callback"],
            "signature": sample_info["signature"],
        }

        request = create_multipart_request(
            sample_info["host"],
            data=fields,
            filename=filename,
            file=file,
        )

        with httpcore.ConnectionPool() as pool:
            response = pool.handle_request(request)
            try:
                body = response.read()
            finally:
                response.close()

        if response.status >= 400:
            raise OSError(
                f"sample upload request failed: status={response.status}, body={body!r}"
            )

        data = json.loads(body)
        data["oss_info"] = sample_info
        return data

    def _do_multipart_upload(
        self, file: BinaryIO, *, bucket: str, object: str, callback: str
    ) -> dict:
        """Upload a file using the OSS multipart protocol."""
        url = f"https://{bucket}.oss-cn-shenzhen.aliyuncs.com/{object}"
        token = self._get_oss_token()
        upload_id = self._oss_multipart_upload_init(url, token)

        parts: list[dict] = []
        part_number = 1
        with httpcore.ConnectionPool() as pool:
            while True:
                # Read a small peek to detect EOF without buffering a full part.
                peek = file.read(256 * 1024)
                if not peek:
                    break

                # part_size is a one-element list so the generator below can
                # accumulate the total and the caller can read it afterwards.
                part_size = [0]

                def _iter_part_content(first_chunk=peek):
                    remaining = MULTIPART_UPLOAD_PART_SIZE - len(first_chunk)
                    part_size[0] += len(first_chunk)
                    yield first_chunk
                    while remaining > 0:
                        buf = file.read(min(256 * 1024, remaining))
                        if not buf:
                            break
                        part_size[0] += len(buf)
                        remaining -= len(buf)
                        yield buf

                part = self._oss_upload_part(
                    url, upload_id, part_number, _iter_part_content(), token, pool
                )
                part["Size"] = part_size[0]
                parts.append(part)
                part_number += 1

        return self._oss_multipart_upload_complete(
            url, upload_id, callback, parts, token
        )

    def _get_oss_token(self) -> dict:
        """Fetch a short-lived STS token from 115 for signing OSS requests."""
        return self._api.get(Endpoint.UPLB + "/3.0/gettoken.php").json()

    def _oss_multipart_upload_init(self, url: str, token: dict) -> str:
        """Initiate an OSS multipart upload session and return the upload_id."""
        init_url = f"{url}?sequential=1&uploads=1"
        headers = self._oss_sign(init_url, "POST", token)
        resp = httpx.post(init_url, headers=headers)
        resp.raise_for_status()
        upload_id = ET.fromstring(resp.content).findtext("UploadId")
        if not upload_id:
            raise RuntimeError(f"UploadId not found in OSS response: {resp.content!r}")
        return upload_id

    def _oss_upload_part(
        self,
        url: str,
        upload_id: str,
        part_number: int,
        content,
        token: dict,
        pool: httpcore.ConnectionPool,
    ) -> dict:
        """Upload one part and return its part metadata dict."""
        part_url = f"{url}?partNumber={part_number}&uploadId={upload_id}"
        headers = self._oss_sign(part_url, "PUT", token)
        # h11 requires Transfer-Encoding: chunked when no Content-Length is known
        headers["transfer-encoding"] = "chunked"
        request = httpcore.Request("PUT", part_url, headers=headers, content=content)
        response = pool.handle_request(request)
        try:
            body = response.read()
        finally:
            response.close()
        if response.status >= 400:
            raise OSError(
                f"part {part_number} upload failed: "
                f"status={response.status}, body={body!r}"
            )
        headers_lower = {k.lower(): v for k, v in response.headers}
        etag = headers_lower.get(b"etag", b"").decode()
        return {"PartNumber": part_number, "ETag": etag}

    def _oss_multipart_upload_complete(
        self,
        url: str,
        upload_id: str,
        callback: dict,
        parts: list[dict],
        token: dict,
    ) -> dict:
        """Finalize the multipart upload and trigger the 115 server callback."""
        complete_url = f"{url}?uploadId={upload_id}"
        xml_body = (
            b"<CompleteMultipartUpload>"
            + b"".join(
                (
                    f"<Part><PartNumber>{p['PartNumber']}</PartNumber>"
                    f"<ETag>{p['ETag']}</ETag></Part>"
                ).encode()
                for p in parts
            )
            + b"</CompleteMultipartUpload>"
        )
        extra_headers = {
            "x-oss-callback": base64.b64encode(callback["callback"].encode()).decode(),
            "x-oss-callback-var": base64.b64encode(
                callback["callback_var"].encode()
            ).decode(),
            "content-type": "text/xml",
        }
        headers = self._oss_sign(complete_url, "POST", token, extra_headers)
        resp = httpx.post(complete_url, headers=headers, content=xml_body)
        resp.raise_for_status()
        return json.loads(resp.content)

    def _oss_sign(
        self,
        url: str,
        method: str,
        token: dict,
        extra_headers: dict | None = None,
    ) -> dict:
        """Build an OSS v1 (HMAC-SHA1) signed headers dict for the given request."""
        headers: dict[str, str] = {}
        if extra_headers:
            headers.update(extra_headers)
        headers["x-oss-security-token"] = token["SecurityToken"]
        headers.setdefault("content-md5", "")
        headers.setdefault("content-type", "")
        date = headers["date"] = formatdate(usegmt=True)

        urlp = urlsplit(url)
        bucket = urlp.hostname.partition(".")[0]
        headers["host"] = urlp.netloc
        headers["referer"] = "https://115.com/"
        headers["user-agent"] = self._api.headers.get("User-Agent", DEFAULT_USER_AGENT)
        oss_header_lines = "\n".join(
            f"{k}:{v}" for k, v in sorted(headers.items()) if k.startswith("x-oss-")
        )
        canonical_resource = (
            f"/{bucket}{urlunsplit(urlp._replace(scheme='', netloc=''))}"
        )
        string_to_sign = (
            f"{method.upper()}\n"
            f"{headers['content-md5']}\n"
            f"{headers['content-type']}\n"
            f"{date}\n"
            f"{oss_header_lines}\n"
            f"{canonical_resource}"
        )
        signature = base64.b64encode(
            hmac.digest(
                token["AccessKeySecret"].encode(),
                string_to_sign.encode(),
                "sha1",
            )
        ).decode()
        headers["authorization"] = f"OSS {token['AccessKeyId']}:{signature}"
        return headers

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
