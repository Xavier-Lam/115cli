"""WebAPI client implementation backed by p115client."""

from __future__ import annotations

from cli115.api.web.p115client import P115Client
from cli115.auth import Auth
from cli115.client.base import AccountClient, Client, DownloadClient, FileClient
from cli115.client.webapi.account import WebAPIAccountClient
from cli115.client.webapi.download import WebAPIDownloadClient
from cli115.client.webapi.file import DEFAULT_USER_AGENT, WebAPIFileClient


__all__ = [
    "DEFAULT_USER_AGENT",
    "WebAPIClient",
]


class WebAPIClient(Client):
    """High-level 115 client backed by the web API.

    Although it is named ``WebAPIClient``, a few of its APIs may come from
    other sources, such as the mobile phone app.
    """

    def __init__(self, auth: Auth):
        self._auth = auth
        api = P115Client(auth.get_cookies())
        self._account = WebAPIAccountClient(api)
        self._file = WebAPIFileClient(api)
        self._download = WebAPIDownloadClient(api)

    @property
    def account(self) -> AccountClient:
        return self._account

    @property
    def file(self) -> FileClient:
        return self._file

    @property
    def download(self) -> DownloadClient:
        return self._download
