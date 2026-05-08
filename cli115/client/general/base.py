from __future__ import annotations

import json
import logging

import httpx
from p115cipher import rsa_decrypt, rsa_encrypt

from cli115.client.models import Directory
from cli115.exceptions import APIError, WAFBlockedError
from cli115.helpers import normalize_path

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)

APP_USER_AGENT = (
    "Mozilla/5.0 115disk/99.99.99.99 115Browser/99.99.99.99 "
    "115wangpan_android/99.99.99.99"
)

APP_VERSION = "99.99.99.99"


logger = logging.getLogger(__name__)


class BaseClient:
    def __init__(self, api: APIClient):
        self._api = api

    def _resolve_dir_id(self, path: str | Directory) -> str:
        if isinstance(path, Directory):
            return path.id
        path = normalize_path(path)
        if path == "/":
            return "0"
        resp = self._api.get(
            Endpoint.WEBAPI + "/files/getid",
            params={"path": path},
        )
        data = resp.json()
        dir_id = str(data["id"])
        if dir_id == "0":
            # the api returns success with id=0 for non-existent paths
            raise FileNotFoundError("directory not found: %s" % path)
        return dir_id


class APIClient(httpx.Client):
    def post_encrypted(
        self,
        url: str,
        **kwargs,
    ) -> httpx.Response:
        data = kwargs.pop("data")
        encrypted_payload = rsa_encrypt(
            json.dumps(data, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        kwargs["data"] = {"data": encrypted_payload}
        resp = self.post(url, **kwargs)
        raw_json = rsa_decrypt(resp.json()["data"])
        resp._content = raw_json
        return resp

    def send(self, request: httpx.Request, *args, **kwargs):
        response = super().send(request, *args, **kwargs)

        self._check_response(response)

        content_type = response.headers.get("Content-Type", "")
        if response.status_code == 405 and content_type.startswith("text/html"):
            body_text = response.text
            if "aliyun.com" in body_text or "alicdn.com" in body_text:
                raise WAFBlockedError("request blocked by Aliyun WAF; try again later")

        response.raise_for_status()

        return response

    def _check_response(self, resp: httpx.Response):
        try:
            data = resp.json()
        except Exception:
            return

        state = data.get("state")
        if state is True or state == 1:
            return

        errno = data.get("errno") or data.get("errNo") or data.get("code") or 0
        if not errno:
            return

        message = (
            data.get("error")
            or data.get("message")
            or data.get("msg")
            or "Unknown API error"
        )
        try:
            raise APIError(message, errno=errno, response=resp)
        except APIError as exc:
            if errno == 990002 or errno == 20018:
                raise FileNotFoundError(exc) from exc
            if errno == 20004:
                raise FileExistsError(exc) from exc
            raise


class Endpoint:
    MY = "https://my.115.com"
    LIXIAN = "https://lixian.115.com"
    PROAPI = "https://proapi.115.com"
    UPLB = "https://uplb.115.com"
    WEBAPI = "https://webapi.115.com"
