from datetime import datetime
from unittest.mock import MagicMock

from httpx import MockTransport, Request, Response

from cli115.client import create_client
from cli115.client.models import Directory, ShareDirectory, ShareFile


def _make_info_response(receive_code: str = "") -> dict:
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


def _share_dir_item(
    cid: str,
    *,
    pid: str = "0",
    name: str = "dir",
    file_count: int = 0,
) -> dict:
    return {
        "cid": cid,
        "pid": pid,
        "n": name,
        "fc": file_count,
        "pc": f"pc-{cid}",
        "tp": 1719044142,
        "te": 1719044142,
    }


def _share_file_item(
    fid: str,
    *,
    cid: str = "0",
    name: str = "file.txt",
    size: int = 123,
) -> dict:
    return {
        "fid": fid,
        "cid": cid,
        "n": name,
        "s": size,
        "sha": "ABC123",
        "ico": "txt",
        "pc": f"pc-{fid}",
        "tp": 1719044142,
        "te": 1719044142,
    }


def _make_list_response(
    items: list[dict], *, count: int, offset: int = 0, limit: int = 200
) -> dict:
    return {
        "state": True,
        "error": "",
        "errno": 0,
        "data": {
            "count": count,
            "offset": offset,
            "limit": limit,
            "list": items,
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
            return Response(200, json=_make_info_response(receive_code="azhy"))

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

    def test_list_root(self):
        captured = {}

        def handler(request: Request) -> Response:
            captured["path"] = request.url.path
            captured["params"] = dict(request.url.params)
            return Response(
                200,
                json=_make_list_response(
                    [
                        _share_dir_item("100", name="movies", file_count=2),
                        _share_file_item("200", name="readme.txt", size=4096),
                    ],
                    count=2,
                    offset=1,
                    limit=2,
                ),
            )

        client = self._make_client(handler)
        try:
            entries, pagination = client.share._list(
                "swzadyu3zs9",
                password="azhy",
                path="/",
                limit=2,
                offset=1,
            )
        finally:
            client.share._api.close()

        assert captured["path"] == "/share/snap"
        assert captured["params"]["share_code"] == "swzadyu3zs9"
        assert captured["params"]["receive_code"] == "azhy"
        assert captured["params"]["cid"] == "0"
        assert captured["params"]["offset"] == "1"
        assert captured["params"]["limit"] == "2"

        assert len(entries) == 2
        assert isinstance(entries[0], ShareDirectory)
        assert entries[0].name == "movies"
        assert entries[0].path == "/movies"

        assert isinstance(entries[1], ShareFile)
        assert entries[1].name == "readme.txt"
        assert entries[1].path == "/readme.txt"
        assert entries[1].size == 4096

        assert pagination.total == 2
        assert pagination.offset == 1
        assert pagination.limit == 2

    def test_list_nested_path(self):
        requests: list[dict[str, str]] = []

        def handler(request: Request) -> Response:
            params = dict(request.url.params)
            requests.append(params)
            cid = params.get("cid", "0")
            if cid == "0":
                return Response(
                    200,
                    json=_make_list_response(
                        [_share_dir_item("100", name="docs")],
                        count=1,
                        offset=0,
                        limit=int(params.get("limit", 200)),
                    ),
                )
            if cid == "100":
                return Response(
                    200,
                    json=_make_list_response(
                        [_share_file_item("201", cid="100", name="guide.txt")],
                        count=1,
                        offset=0,
                        limit=int(params.get("limit", 200)),
                    ),
                )
            raise AssertionError(f"unexpected cid: {cid}")

        client = self._make_client(handler)
        try:
            entries, _ = client.share._list(
                "swzadyu3zs9",
                password="azhy",
                path="/docs",
                limit=10,
                offset=0,
            )
        finally:
            client.share._api.close()

        assert [req["cid"] for req in requests] == ["0", "100"]
        assert all(req["share_code"] == "swzadyu3zs9" for req in requests)
        assert all(req["receive_code"] == "azhy" for req in requests)

        assert len(entries) == 1
        assert isinstance(entries[0], ShareFile)
        assert entries[0].name == "guide.txt"
        assert entries[0].path == "/docs/guide.txt"

    def test_stat_nested_file(self):
        requests: list[dict[str, str]] = []

        def handler(request: Request) -> Response:
            params = dict(request.url.params)
            requests.append(params)
            cid = params.get("cid", "0")
            if cid == "0":
                return Response(
                    200,
                    json=_make_list_response(
                        [_share_dir_item("100", name="docs")],
                        count=1,
                    ),
                )
            if cid == "100":
                return Response(
                    200,
                    json=_make_list_response(
                        [_share_file_item("201", cid="100", name="guide.txt")],
                        count=1,
                    ),
                )
            raise AssertionError(f"unexpected cid: {cid}")

        client = self._make_client(handler)
        try:
            entry = client.share.stat(
                "swzadyu3zs9",
                "/docs/guide.txt",
                password="azhy",
            )
        finally:
            client.share._api.close()

        assert [req["cid"] for req in requests] == ["0", "100"]
        assert isinstance(entry, ShareFile)
        assert entry.id == "201"
        assert entry.parent_id == "100"
        assert entry.name == "guide.txt"
        assert entry.path == "/docs/guide.txt"

    def test_stat_root(self):
        def handler(_: Request) -> Response:
            raise AssertionError("root stat should not call API")

        client = self._make_client(handler)
        try:
            entry = client.share.stat("swzadyu3zs9", "/", password="azhy")
        finally:
            client.share._api.close()

        assert isinstance(entry, Directory)
        assert entry.id == "0"
        assert entry.path == "/"
