from __future__ import annotations

from cli115.client.base import ShareClient as BaseShareClient
from cli115.client.models import ShareInfo
from cli115.client.utils import parse_ts
from .base import BaseClient, Endpoint


class ShareClient(BaseShareClient, BaseClient):

    def info(self, share_code: str, password: str | None = None) -> ShareInfo:
        receive_code = (password or "").strip()

        params = {
            "share_code": share_code,
            "limit": 1,
        }
        if receive_code:
            params["receive_code"] = receive_code

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
