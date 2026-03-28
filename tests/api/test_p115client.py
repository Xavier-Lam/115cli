import pytest

from cli115.api.web.p115client import check_response
from cli115.exceptions import (
    APIError,
    AlreadyExistsError,
    NotFoundError,
)


class TestCheckResponse:

    def test_returns_resp_when_state_true(self):
        resp = {"state": True, "data": []}
        result = check_response(resp)
        assert result is resp

    def test_returns_resp_when_state_one(self):
        resp = {"state": 1, "data": []}
        result = check_response(resp)
        assert result is resp

    def test_raises_not_found_for_errno_990002(self):
        resp = {"state": False, "errno": 990002, "error": "not found"}
        with pytest.raises(NotFoundError) as exc_info:
            check_response(resp)
        assert exc_info.value.errno == 990002

    def test_raises_already_exists_for_errno_20004(self):
        resp = {"state": False, "errno": 20004, "error": "exists"}
        with pytest.raises(AlreadyExistsError) as exc_info:
            check_response(resp)
        assert exc_info.value.errno == 20004

    def test_raises_api_error_for_other_errno(self):
        resp = {"state": False, "errno": 99999, "error": "something"}
        with pytest.raises(APIError) as exc_info:
            check_response(resp)
        assert exc_info.value.errno == 99999

    def test_uses_errNo_field(self):
        resp = {"state": False, "errNo": 990002, "error": "nf"}
        with pytest.raises(NotFoundError):
            check_response(resp)

    def test_default_message_when_no_error_field(self):
        resp = {"state": False, "errno": 1}
        with pytest.raises(APIError) as exc_info:
            check_response(resp)
        assert "Unknown API error" in str(exc_info.value)
