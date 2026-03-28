import logging
from property import locked_cacheproperty

from httpcore_request import HTTPStatusError
from p115client import P115Client as BaseP115Client

from cli115.exceptions import (
    APIError,
    AlreadyExistsError,
    NotFoundError,
    WAFBlockedError,
)


logger = logging.getLogger(__name__)


class P115Client(BaseP115Client):
    """
    A wrapper around P115Client to add WAF block detection and userkey correction.
    """

    def request(
        self,
        /,
        url,
        method="GET",
        payload=None,
        *,
        ecdh_encrypt=False,
        request=None,
        async_=False,
        **request_kwargs,
    ):
        try:
            message = f"Requesting {method} {url}"
            params = request_kwargs.get("params")
            if params:
                message += f"\n    └─ Params: {params}"
            data = request_kwargs.get("data")
            if data is not None:
                message += f"\n    └─ Payload: {data}"
            logger.debug(message)

            return super().request(
                url,
                method,
                payload,
                ecdh_encrypt=ecdh_encrypt,
                request=request,
                async_=async_,
                **request_kwargs,
            )
        except HTTPStatusError as exc:
            if self._is_waf_blocked(exc):
                raise WAFBlockedError(
                    "Request blocked by Aliyun WAF; try again later"
                ) from exc
            raise

    @locked_cacheproperty
    def user_key(self) -> str:
        # fetch userkey via /app/uploadinfo (works with web cookies) to avoid
        # the default /android/2.0/user/upload_key endpoint which requires
        # app-specific cookies (errno 99).
        resp = self.upload_info()
        check_response(resp)
        return resp["userkey"]

    @staticmethod
    def _is_waf_blocked(exc: HTTPStatusError) -> bool:
        """Return True if the error is an Aliyun WAF block (HTTP 405 with WAF body)."""
        if exc.code != 405 or not dict(exc.headers).get("Content-Type", "").startswith(
            "text/html"
        ):
            return False
        body_text = exc.response_body.decode("utf-8", errors="replace")
        return "aliyun.com" in body_text or "alicdn.com" in body_text


def check_response(resp: dict) -> dict:
    state = resp.get("state")
    if state is True or state == 1:
        return resp
    errno = resp.get("errno") or resp.get("errNo") or resp.get("code") or 0
    message = (
        resp.get("error")
        or resp.get("message")
        or resp.get("msg")
        or "Unknown API error"
    )
    if errno == 990002 or errno == 20018:
        raise NotFoundError(message, errno=errno)
    if errno == 20004:
        raise AlreadyExistsError(message, errno=errno)
    raise APIError(message, errno=errno)
