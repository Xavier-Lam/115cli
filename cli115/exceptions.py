"""Exception hierarchy for cli115."""

from httpx import Response


class APIError(Exception):
    """Base exception for all cli115 errors.

    Wraps errors returned by the 115 API.
    """

    def __init__(self, message: str, errno: int = 0, response: Response | None = None):
        self.errno = errno
        self.response = response
        message = f"[{errno}] {message}" if errno else message
        if response is not None and response._request:
            message = f"{message} (URL: {response.url})"
        super().__init__(message)


class InstantUploadNotAvailableError(Exception):
    """Raised when instant upload is requested but the file is not available
    on the server (i.e. the file has never been uploaded before).

    Attributes:
        response_data: The decoded initupload.php response dict (status=1),
            containing ``bucket``, ``object`` and ``callback`` fields that
            callers can use to perform a regular or multipart upload.
    """

    def __init__(self, message: str = "", *, response_data: dict | None = None):
        self.response_data = response_data
        super().__init__(message)


class WAFBlockedError(Exception):
    """Raised when requests are blocked by Aliyun WAF.

    This happens when too many requests are sent in a short period of time.
    Wait a while before retrying.  The error may manifest either as an HTTP 405
    response (WAF intercepts the request at the HTTP level).
    """


class CredentialError(Exception):
    """Raised when credentials are missing or invalid."""


class CommandLineError(Exception):
    """Friendly error message for CLI command failures."""
