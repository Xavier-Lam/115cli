"""Base auth interface for cli115."""

from abc import ABC, abstractmethod


class Auth(ABC):
    """Abstract base class for authentication providers.

    Subclasses provide cookies that the client uses for API requests.
    """

    @abstractmethod
    def get_cookies(self) -> dict[str, str]:
        """Return cookie key-value pairs for 115 API authentication."""
