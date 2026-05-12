from __future__ import annotations

from httpx import BaseTransport

from cli115.auth import Auth
from cli115.client.base import Client as BaseClient
from .base import APIClient, DEFAULT_USER_AGENT
from .account import AccountClient
from .download import DownloadClient
from .file import FileClient
from .share import ShareClient
from .stream import StreamClient

__all__ = [
    "Client",
    "DEFAULT_USER_AGENT",
]


class Client(BaseClient):
    """High-level 115 client

    The client uses API endpoints available to general users. Mostly from the web
    interface.
    """

    def __init__(self, auth: Auth, transport: BaseTransport | None = None):
        api = APIClient(
            cookies=auth.get_cookies(),
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Referer": "https://115.com/",
                "Origin": "https://115.com",
            },
            transport=transport,
        )
        super().__init__(
            account=AccountClient(api),
            file=FileClient(api),
            download=DownloadClient(api),
            share=ShareClient(api),
            stream=StreamClient(api),
        )
