import json

from httpx import Client as _Client, Request, RequestNotRead, Response
from p115cipher import rsa_decrypt, rsa_encrypt

from cli115.api.web.p115client import check_response, logger
from cli115.exceptions import WAFBlockedError

__all__ = [
    "Client",
]


class Client(_Client):
    def post_encrypted(
        self,
        url: str,
        **kwargs,
    ) -> Response:
        data = kwargs.pop("data")
        encrypted_payload = rsa_encrypt(
            json.dumps(data, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        kwargs["data"] = {"data": encrypted_payload}
        resp = self.post(url, **kwargs)
        raw_json = rsa_decrypt(resp.json()["data"])
        resp._content = raw_json
        return resp

    def send(self, request: Request, *args, **kwargs):
        message = (
            f"Requesting {request.method} "
            f"{request.url.scheme}://{request.url.host}{request.url.path}"
        )
        params = request.url.params
        if params:
            message += f"\n    └─ Params: {params}"
        try:
            data = request.content
        except RequestNotRead:
            data = b"<streaming request body>"
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
