from __future__ import annotations

import base64
from email.utils import formatdate
import hashlib
import hmac
import json
from typing import BinaryIO
from urllib.parse import urlparse, urlsplit, urlunsplit
import uuid
import xml.etree.ElementTree as ET

import httpcore
import httpx
from p115cipher import ecdh_aes_decrypt, make_upload_payload

from cli115.exceptions import InstantUploadNotAvailableError
from .base import (
    APP_USER_AGENT,
    APP_VERSION,
    APIClient,
    DEFAULT_USER_AGENT,
    Endpoint,
)

# 16 MB per chunk; also used as the threshold for switching to multipart upload
MULTIPART_UPLOAD_PART_SIZE = 16 * 1024 * 1024

_CHUNK_SIZE = 64 * 1024


class UploadClient:
    """Handles all upload-related operations.

    Provides two public upload methods:
      - ``simple_upload``: single-request upload via the sample-upload endpoint.
      - ``multipart_upload``: OSS multipart upload for large files.
    """

    def __init__(self, api: APIClient):
        self._api = api
        self._client = httpx.Client(
            headers={
                "User-Agent": api.headers.get("User-Agent", DEFAULT_USER_AGENT),
                "Referer": "https://115.com/",
            }
        )

    def instant_upload(
        self,
        *,
        file: BinaryIO,
        filename: str,
        file_size: int,
        sha1: str,
        dir_id: str,
    ) -> None:
        """Attempt an instant upload (zero-copy if the file is already on 115).

        Raises:
            InstantUploadNotAvailableError: If the server does not have the file,
                with ``response_data`` carrying the initupload response so the
                caller can reuse bucket/object/callback for a multipart upload.
        """

        def read_range(range_str: str) -> bytes:
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

    def simple_upload(self, file: BinaryIO, *, pid: str, filename: str) -> dict:
        """Upload a file using the simple (sample) upload endpoint.

        Args:
            file: Readable binary file object (seeked to start).
            pid: Parent directory ID on 115.
            filename: Destination filename.

        Returns:
            Parsed JSON response from the upload callback.
        """
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

        request = self._create_multipart_request(
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

    def multipart_upload(
        self, file: BinaryIO, *, bucket: str, object: str, callback: str
    ) -> dict:
        """Upload a file using the OSS multipart protocol.

        Args:
            file: Readable binary file object (seeked to start).
            bucket: OSS bucket name.
            object: OSS object key.
            callback: Serialised callback payload from the initupload response.

        Returns:
            Parsed JSON response from the OSS complete-upload callback.
        """
        url = f"https://{bucket}.oss-cn-shenzhen.aliyuncs.com/{object}"
        token = self._get_oss_token()
        upload_id = self._oss_multipart_upload_init(url, token)

        parts: list[dict] = []
        part_number = 1
        with httpcore.ConnectionPool() as pool:
            while True:
                # Read a small peek to detect EOF without buffering a full part.
                peek = file.read(_CHUNK_SIZE)
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
                        buf = file.read(min(_CHUNK_SIZE, remaining))
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

    def _get_oss_token(self) -> dict:
        """Fetch a short-lived STS token from 115 for signing OSS requests."""
        return self._api.get(Endpoint.UPLB + "/3.0/gettoken.php").json()

    def _oss_multipart_upload_init(self, url: str, token: dict) -> str:
        """Initiate an OSS multipart upload session and return the upload_id."""
        init_url = f"{url}?sequential=1&uploads=1"
        headers = self._oss_sign(init_url, "POST", token)
        resp = self._client.post(init_url, headers=headers)
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
        resp = self._client.post(complete_url, headers=headers, content=xml_body)
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

    def _create_multipart_request(
        self,
        url: str,
        *,
        data: dict[str, str],
        filename: str,
        file: BinaryIO,
    ) -> httpcore.Request:
        parsed = urlparse(url)
        boundary = uuid.uuid4().hex
        content = self._iter_multipart_content(
            boundary=boundary,
            data=data,
            filename=filename,
            file=file,
        )
        return httpcore.Request(
            method="POST",
            url=url,
            headers={
                "Host": parsed.netloc,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Transfer-Encoding": "chunked",
            },
            content=content,
        )

    def _iter_multipart_content(
        self,
        *,
        boundary: str,
        data: dict[str, str],
        filename: str,
        file: BinaryIO,
    ):
        boundary_bytes = boundary.encode("ascii")

        for key, value in data.items():
            yield b"--" + boundary_bytes + b"\r\n"
            yield (f'Content-Disposition: form-data; name="{key}"\r\n\r\n').encode(
                "utf-8"
            )
            yield str(value).encode("utf-8")
            yield b"\r\n"

        yield b"--" + boundary_bytes + b"\r\n"
        yield (
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        ).encode("utf-8")
        yield b"Content-Type: application/octet-stream\r\n\r\n"

        while chunk := file.read(_CHUNK_SIZE):
            yield chunk

        yield b"\r\n"
        yield b"--" + boundary_bytes + b"--\r\n"
