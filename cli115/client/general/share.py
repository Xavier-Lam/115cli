from __future__ import annotations

import os

from cli115.client.base import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    ShareClient as BaseShareClient,
)
from cli115.client.models import Pagination, ShareDirectory, ShareFile, ShareInfo
from cli115.client.utils import parse_item, parse_ts
from cli115.helpers import join_path, normalize_path
from .base import BaseClient, Endpoint


class ShareClient(BaseShareClient, BaseClient):

    def info(self, share_code: str, password: str | None = None) -> ShareInfo:
        receive_code = (password or "").strip()
        params = self._base_params(share_code, receive_code)
        params["limit"] = 1

        resp = self._api.get(
            Endpoint.WEBAPI + "/share/snap",
            params=params,
        )
        data = resp.json()["data"]

        shareinfo = data["shareinfo"]
        userinfo = data["userinfo"]

        created_time = parse_ts(shareinfo.get("create_time"))
        expire_raw = shareinfo.get("expire_time")
        expire_time = (
            None if str(expire_raw) in {"", "0", "-1", "None"} else parse_ts(expire_raw)
        )

        return ShareInfo(
            share_code=share_code,
            share_id=shareinfo.get("snap_id", ""),
            title=shareinfo.get("share_title", ""),
            owner_id=userinfo.get("user_id", ""),
            owner_name=userinfo.get("user_name", ""),
            has_password=bool(shareinfo.get("has_receive_code", 0)),
            receive_code=shareinfo.get("receive_code") or receive_code,
            receive_count=shareinfo.get("receive_count", 0),
            item_count=data.get("count", 0),
            total_size=shareinfo.get("file_size", 0),
            created_time=created_time,
            expire_time=expire_time,
            is_available=shareinfo["share_state"] == 1,
        )

    def stat(
        self,
        share_code: str,
        path: str,
        password: str | None = None,
    ) -> ShareDirectory | ShareFile:
        return self._resolve_entry(share_code, path, password=password)

    def _list(
        self,
        share_code: str,
        password: str | None = None,
        path: str | ShareDirectory = "/",
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> tuple[list[ShareDirectory | ShareFile], Pagination]:
        if isinstance(path, ShareDirectory):
            dir_id = path.id
            dir_path = path.path or "/"
        else:
            dir_path = normalize_path(path)
            if dir_path == "/":
                dir_id = "0"
            else:
                entry = self._resolve_entry(share_code, dir_path, password=password)
                if not entry.is_directory:
                    raise NotADirectoryError(f"not a directory: {dir_path}")
                dir_id = entry.id

        receive_code = (password or "").strip()
        payload = self._base_params(share_code, receive_code)
        payload.update(
            {
                "cid": dir_id,
                "offset": offset,
                "limit": min(limit, MAX_PAGE_SIZE),
            }
        )

        resp = self._api.get(
            Endpoint.WEBAPI + "/share/snap",
            params=payload,
        ).json()
        data = resp["data"]

        items: list[ShareDirectory | ShareFile] = []
        for raw in data.get("list", []):
            item = parse_item(raw, share=True)
            item.path = join_path(dir_path, item.name)
            items.append(item)

        pagination = Pagination(
            total=int(data.get("count", 0)),
            offset=int(data.get("offset", offset)),
            limit=int(data.get("limit", min(limit, MAX_PAGE_SIZE))),
        )
        return items, pagination

    def _resolve_entry(
        self,
        share_code: str,
        path: str,
        *,
        password: str | None = None,
    ) -> ShareDirectory | ShareFile:
        path = normalize_path(path)
        if path == "/":
            return ShareDirectory(
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
        for entry in self.list(share_code, password=password, path=dirname):
            if entry.name == name:
                return entry
        raise FileNotFoundError(f"entry not found: {path}")

    def _base_params(self, share_code: str, receive_code: str) -> dict[str, object]:
        params = {"share_code": share_code}
        if receive_code:
            params["receive_code"] = receive_code
        return params
