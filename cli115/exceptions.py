"""Exception hierarchy for cli115."""


class APIError(Exception):
    """Base exception for all cli115 errors.

    Wraps errors returned by the 115 API.
    """

    def __init__(self, message: str, errno: int = 0):
        self.errno = errno
        super().__init__(f"[{errno}] {message}")


class AuthenticationError(APIError):
    """Raised when authentication fails or credentials are invalid."""


class SessionExpiredError(AuthenticationError):
    """Raised when the session has expired."""


class NotFoundError(APIError):
    """Raised when a requested file or directory is not found."""


class AlreadyExistsError(APIError):
    """Raised when a resource with the same name already exists."""


class PermissionDeniedError(APIError):
    """Raised when the user lacks permission."""


class InvalidParameterError(APIError):
    """Raised when an API call receives invalid parameters."""


class DirectoryNotEmptyError(APIError):
    """Raised when attempting to delete a non-empty directory non-recursively."""


class WAFBlockedError(APIError):
    """Raised when requests are blocked by Aliyun WAF.

    This happens when too many requests are sent in a short period of time.
    Wait a while before retrying.  The error may manifest either as an HTTP 405
    response (WAF intercepts the request at the HTTP level).
    """
