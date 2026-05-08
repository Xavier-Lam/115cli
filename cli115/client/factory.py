"""Factory for creating high-level clients."""

from httpx import BaseTransport

from cli115.auth import Auth
from cli115.client.base import Client
from cli115.client import general


def create_client(auth: Auth, transport: BaseTransport | None = None) -> Client:
    """Create a high-level Client from an Auth provider.

    The auth object is retained by the client so it can
    be used for session refresh in the future.

    Args:
        auth: An authentication provider.

    Returns:
        A Client instance.
    """
    return general.Client(auth, transport=transport)
