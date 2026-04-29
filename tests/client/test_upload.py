import hashlib
import io
import unittest.mock
import uuid
from unittest.mock import MagicMock, patch

import pytest

from cli115.client import File, UploadStatus, webapi
from cli115.exceptions import InstantUploadNotAvailableError
from tests.client.conftest import upload_file


class TestUpload:

    def test_upload_file(self, api_client, root_dir):
        entry = upload_file(api_client, root_dir.path, size=1024)
        assert isinstance(entry, File)
        assert entry.size == 1024

    def test_upload_file_like_object(self, api_client, root_dir):
        content = uuid.uuid4().bytes * 64
        expected_sha1 = hashlib.sha1(content).hexdigest().upper()
        buf = io.BytesIO(content)
        buf.name = f"up_buf_{uuid.uuid4().hex[:8]}.bin"
        result = api_client.file.upload(f"{root_dir.path}/{buf.name}", buf)
        assert isinstance(result, File)
        assert result.sha1 == expected_sha1

    def test_upload_file_already_exists(self, api_client, shared):
        with pytest.raises(FileExistsError):
            api_client.file.upload(shared.file_small.path, io.BytesIO(b"new content"))
        # confirm the file is unchanged after the failed upload
        unchanged = api_client.file.stat(shared.file_small.path)
        assert unchanged.sha1 == shared.file_small.sha1
        assert unchanged.size == shared.file_small.size


class TestInstantUpload:

    _INSTANT_CONTENT = b"a" * 4096 * 1024  # 4 MB - known content for server-side
    _INSTANT_SHA1 = hashlib.sha1(_INSTANT_CONTENT).hexdigest().upper()

    @pytest.fixture
    def mock_client(self):
        """WebAPIClient with fully mocked API - makes no actual network requests."""
        with patch("cli115.client.webapi.P115Client"):
            client = webapi.WebAPIClient(MagicMock())
        mock_api = MagicMock()
        client._file._api = mock_api
        # stat raises FileNotFoundError so _upload proceeds past the duplicate check
        client.file.stat = MagicMock(side_effect=FileNotFoundError("path not found"))
        # parent directory always resolves to a fake dir ID
        client.file._resolve_dir_id = MagicMock(return_value="1234")
        return client

    def test_instant_upload_success(self, api_client, root_dir):
        path = f"{root_dir.path}/instant.bin"
        file = io.BytesIO(self._INSTANT_CONTENT)
        status = UploadStatus()
        with unittest.mock.patch.object(
            api_client.file._api, "upload_file_sample"
        ) as mock_sample:
            result = api_client.file.upload(path, file, status=status)
        assert isinstance(result, File)
        assert result.sha1 == self._INSTANT_SHA1
        mock_sample.assert_not_called()
        assert status.is_instant_uploaded is True
        assert status.instant_upload_error is None

        info = api_client.file.id(result.id)
        assert info.sha1 == self._INSTANT_SHA1

    def test_instant_only_raises(self, mock_client):
        file = io.BytesIO(self._INSTANT_CONTENT)
        mock_client.file._api.upload_file_init.return_value = {"reuse": 0}
        with pytest.raises(InstantUploadNotAvailableError):
            # _INSTANT_CONTENT is 4 MB; a 4 MB threshold forces instant-only mode
            mock_client.file.upload("/remote/f.bin", file, instant_only=4 * 1024 * 1024)

    def test_small_file_skips_instant_upload(self, mock_client):
        file = io.BytesIO(b"small content")
        mock_client.file._api.upload_file_sample.return_value = (
            self._fake_upload_response("f.bin", "sha1", len(b"small content"))
        )
        status = UploadStatus()
        mock_client.file.upload("/remote/f.bin", file, status=status)

        mock_client.file._api.upload_file_init.assert_not_called()
        assert status.is_instant_uploaded is False
        assert status.instant_upload_error is None

    def test_nonexist_fallback(self, mock_client):
        file = io.BytesIO(self._INSTANT_CONTENT)
        mock_client.file._api.upload_file_init.return_value = {"reuse": 0}
        mock_client.file._api.upload_file_sample.return_value = (
            self._fake_upload_response(
                "f.bin", self._INSTANT_SHA1, len(self._INSTANT_CONTENT)
            )
        )
        status = UploadStatus()
        result = mock_client.file.upload("/remote/f.bin", file, status=status)

        mock_client.file._api.upload_file_sample.assert_called_once()

        assert isinstance(result, File)
        assert result.sha1.upper() == self._INSTANT_SHA1
        assert status.is_instant_uploaded is False
        assert isinstance(status.instant_upload_error, InstantUploadNotAvailableError)

    def test_exception_fallback(self, mock_client):
        file = io.BytesIO(self._INSTANT_CONTENT)
        err_msg = "simulated instant upload failure"
        mock_client.file._api.upload_file_init.side_effect = RuntimeError(err_msg)
        mock_client.file._api.upload_file_sample.return_value = (
            self._fake_upload_response(
                "f.bin", self._INSTANT_SHA1, len(self._INSTANT_CONTENT)
            )
        )
        status = UploadStatus()
        result = mock_client.file.upload("/remote/f.bin", file, status=status)
        assert isinstance(result, File)
        assert result.sha1.upper() == self._INSTANT_SHA1
        assert status.instant_upload_error is not None
        assert err_msg in str(status.instant_upload_error)
        mock_client.file._api.upload_file_sample.assert_called_once()

    @staticmethod
    def _fake_upload_response(name: str, sha1: str, size: int) -> dict:
        return {
            "state": True,
            "data": {
                "file_id": "999",
                "file_name": name,
                "pick_code": "pc",
                "file_ptime": None,
                "sha1": sha1,
                "file_size": size,
            },
        }
