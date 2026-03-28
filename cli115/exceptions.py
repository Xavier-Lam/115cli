"""Exception hierarchy for cli115."""


class APIError(Exception):
    """Base exception for all cli115 errors.

    Wraps errors returned by the 115 API.
    """

    def __init__(self, message: str, errno: int = 0):
        self.errno = errno
        message = f"[{errno}] {message}" if errno else message
        super().__init__(message)


class NotFoundError(APIError):
    """Raised when a requested file or directory is not found."""


class AlreadyExistsError(APIError):
    """Raised when a resource with the same name already exists."""


class WAFBlockedError(APIError):
    """Raised when requests are blocked by Aliyun WAF.

    This happens when too many requests are sent in a short period of time.
    Wait a while before retrying.  The error may manifest either as an HTTP 405
    response (WAF intercepts the request at the HTTP level).
    """


class InstantUploadNotAvailableError(APIError):
    """Raised when instant upload is requested but the file is not available
    on the server (i.e. the file has never been uploaded before)."""


class CommandLineError(Exception):
    """Friendly error message for CLI command failures."""

    pass
