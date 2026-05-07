from httpx import Client as _Client, Request

from cli115.api.web.p115client import check_response, logger
from cli115.exceptions import WAFBlockedError

__all__ = [
    "Client",
]


class Client(_Client):
    def send(self, request: Request, *args, **kwargs):
        message = f"Requesting {request.method} {request.url.scheme}://{request.url.host}{request.url.path}"
        params = request.url.params
        if params:
            message += f"\n    └─ Params: {params}"
        data = request.content
        if data:
            message += f"\n    └─ Payload: {data}"
        logger.debug(message)

        response = super().send(request, *args, **kwargs)

        content_type = response.headers.get("Content-Type", "")
        if content_type.startswith("application/json"):
            # check_response will raise an exception if the response indicates an error
            check_response(response.json())

        if response.status_code == 405 and content_type.startswith("text/html"):
            body_text = response.text
            if "aliyun.com" in body_text or "alicdn.com" in body_text:
                raise WAFBlockedError("request blocked by Aliyun WAF; try again later")

        response.raise_for_status()

        return response
