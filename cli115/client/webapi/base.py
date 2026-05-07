from __future__ import annotations

from cli115.api import Client, endpoint
from cli115.api.web.p115client import P115Client
from cli115.client.models import Directory
from cli115.helpers import normalize_path

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)


class BaseClient:
    def __init__(self, api: P115Client):
        self._api = api
        self._client = Client(
            cookies={c: api.cookies[c].value for c in api.cookies},
            headers={"User-Agent": DEFAULT_USER_AGENT},
        )

    def _resolve_dir_id(self, path: str | Directory) -> str:
        if isinstance(path, Directory):
            return path.id
        path = normalize_path(path)
        if path == "/":
            return "0"
        resp = self._client.get(
            endpoint.WEBAPI + "/files/getid",
            params={"path": path},
        )
        data = resp.json()
        dir_id = str(data["id"])
        if dir_id == "0":
            # the api returns success with id=0 for non-existent paths
            raise FileNotFoundError("directory not found: %s" % path)
        return dir_id
