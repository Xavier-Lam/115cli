from __future__ import annotations

from cli115.api.web.p115client import check_response, P115Client
from cli115.client.models import Directory
from cli115.helpers import normalize_path


class BaseClient:
    def __init__(self, api: P115Client):
        self._api = api

    def _resolve_dir_id(self, path: str | Directory) -> str:
        if isinstance(path, Directory):
            return path.id
        path = normalize_path(path)
        if path == "/":
            return "0"
        resp = self._api.fs_dir_getid({"path": path})
        resp = check_response(resp)
        dir_id = str(resp["id"])
        if dir_id == "0":
            # the api returns success with id=0 for non-existent paths
            raise FileNotFoundError("directory not found: %s" % path)
        return dir_id
