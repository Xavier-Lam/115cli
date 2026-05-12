from __future__ import annotations

from urllib.parse import urlencode

import m3u8

from cli115.client.base import StreamClient as BaseStreamClient
from cli115.client.models import File
from .base import BaseClient, Endpoint


class StreamClient(BaseStreamClient, BaseClient):

    def info(self, pickcode: str | File, /) -> dict:
        if isinstance(pickcode, File):
            pickcode = pickcode.pickcode
        resp = self._api.get(
            Endpoint.WEBAPI + "/files/video",
            params={"pickcode": pickcode},
        )
        return resp.json()

    def get_m3u8(self, pickcode: str | File, /) -> m3u8.M3U8:
        if isinstance(pickcode, File):
            pickcode = pickcode.pickcode
        url = Endpoint.MAIN + f"/api/video/m3u8/{pickcode}.m3u8"
        resp = self._api.get(url, params={"definition": 0})
        return m3u8.loads(resp.content.decode("utf-8"), uri=url)

    def transcode_status(self, video: File, /) -> dict:
        resp = self._api.post(
            Endpoint.TRANSCODE + "/api/1.0/web/1.0/trans_code/check_transcode_job",
            params={"sha1": video.sha1, "priority": 100},
            json={"fid": video.id},
        )
        return resp.json()

    def accelerate_transcode(self, video: File) -> None:
        referrer = (
            Endpoint.MAIN
            + f"/players/video/{video.pickcode}?"
            + urlencode(
                {
                    "name": video.name,
                    "fid": video.id,
                }
            )
        )
        self._api.post(
            Endpoint.MAIN + "/?ct=play&ac=push",
            data={"op": "vip_push", "pickcode": video.pickcode, "sha1": video.sha1},
            headers={"Referer": referrer},
        )
