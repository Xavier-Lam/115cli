from datetime import datetime
from unittest.mock import MagicMock

from httpx import MockTransport, Request, Response

from cli115.client import create_client


def _make_response(receive_code: str = "") -> dict:
    return {
        "state": True,
        "error": "",
        "errno": 0,
        "data": {
            "userinfo": {
                "user_id": "337137737",
                "user_name": "test-user",
            },
            "shareinfo": {
                "snap_id": "308465423",
                "file_size": 42056430,
                "share_title": "sample share",
                "share_state": 1,
                "create_time": 1719044142,
                "receive_code": receive_code,
                "has_receive_code": int(bool(receive_code)),
                "receive_count": 337,
                "expire_time": -1,
            },
            "count": 1,
            "list": [],
            "share_state": 1,
        },
    }


class TestShareClient:
    def _make_client(self, handler):
        auth = MagicMock()
        auth.get_cookies.return_value = {}
        return create_client(auth, transport=MockTransport(handler))

    def test_info_with_password(self):
        captured = {}

        def handler(request: Request) -> Response:
            captured["path"] = request.url.path
            captured["params"] = dict(request.url.params)
            return Response(200, json=_make_response(receive_code="azhy"))

        client = self._make_client(handler)
        try:
            info = client.share.info("swzadyu3zs9", password="azhy")
        finally:
            client.share._api.close()

        assert captured["path"] == "/share/snap"
        assert captured["params"]["share_code"] == "swzadyu3zs9"
        assert captured["params"]["receive_code"] == "azhy"
        assert captured["params"]["limit"] == "1"

        assert info.share_code == "swzadyu3zs9"
        assert info.share_id == "308465423"
        assert info.title == "sample share"
        assert info.owner_id == "337137737"
        assert info.owner_name == "test-user"
        assert info.has_password is True
        assert info.receive_code == "azhy"
        assert info.receive_count == 337
        assert info.item_count == 1
        assert info.total_size == 42056430
        assert info.created_time == datetime.fromtimestamp(1719044142)
        assert info.expire_time is None
        assert info.is_available is True
