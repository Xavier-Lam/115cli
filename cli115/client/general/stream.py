from __future__ import annotations

import m3u8

from cli115.client.base import StreamClient as BaseStreamClient
from cli115.client.models import File
from .base import BaseClient


class StreamClient(BaseStreamClient, BaseClient):

    def get_m3u8(self, pickcode: str | File, /) -> m3u8.M3U8:
        if isinstance(pickcode, File):
            pickcode = pickcode.pickcode
        url = f"https://115.com/api/video/m3u8/{pickcode}.m3u8"
        resp = self._api.get(url, params={"definition": 0})
        return m3u8.loads(resp.content.decode("utf-8"), uri=url)
