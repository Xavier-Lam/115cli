from __future__ import annotations

from datetime import datetime

from cli115.api.web.p115client import check_response
from cli115.client.base import AccountClient
from cli115.client.models import AccountInfo, Usage
from cli115.client.webapi.base import BaseClient


class WebAPIAccountClient(AccountClient, BaseClient):

    def info(self) -> AccountInfo:
        resp = self._api.user_my()
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

    def usage(self) -> Usage:
        resp = self._api.fs_index_info()
        check_response(resp)
        space = resp.get("data", {}).get("space_info", {})
        return Usage(
            total=int(space.get("all_total", {}).get("size", 0)),
            used=int(space.get("all_use", {}).get("size", 0)),
            remaining=int(space.get("all_remain", {}).get("size", 0)),
        )
