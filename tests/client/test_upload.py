import hashlib
import io
import unittest.mock
import uuid
import warnings

import pytest

from cli115.client import File, webapi
from cli115.exceptions import AlreadyExistsError, InstantUploadNotAvailableError
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
        with pytest.raises(AlreadyExistsError):
            api_client.file.upload(shared.file_small.path, io.BytesIO(b"new content"))
        # confirm the file is unchanged after the failed upload
        unchanged = api_client.file.stat(shared.file_small.path)
        assert unchanged.sha1 == shared.file_small.sha1
        assert unchanged.size == shared.file_small.size


class TestInstantUpload:

    _INSTANT_CONTENT = b"a" * 4096 * 1024
    _INSTANT_SHA1 = hashlib.sha1(_INSTANT_CONTENT).hexdigest().upper()
    _MINIMUN_INSTANT_CONTENT = b"a" * 64 * 1024
    _MINIMUM_INSTANT_SHA1 = hashlib.sha1(_MINIMUN_INSTANT_CONTENT).hexdigest().upper()

    def setup_method(self):
        self._original_min_instant_size = webapi.MIN_INSTANT_UPLOAD_SIZE
        webapi.MIN_INSTANT_UPLOAD_SIZE = 64 * 1024

    def teardown_method(self):
        webapi.MIN_INSTANT_UPLOAD_SIZE = self._original_min_instant_size

    def _upload_path(self, root_dir):
        fname = f"instant_{uuid.uuid4().hex[:8]}.bin"
        return f"{root_dir.path}/{fname}"

    def test_instant_upload_success(self, api_client, root_dir):
        path = self._upload_path(root_dir)
        file = io.BytesIO(self._INSTANT_CONTENT)
        with unittest.mock.patch.object(
            api_client._api, "upload_file_sample"
        ) as mock_sample:
            result = api_client.file.upload(path, file)
        assert isinstance(result, File)
        assert result.sha1 == self._INSTANT_SHA1
        mock_sample.assert_not_called()

        info = api_client.file.id(result.id)
        assert info.sha1 == self._INSTANT_SHA1

    def test_instant_only_raises(self, api_client, root_dir):
        path = self._upload_path(root_dir)
        file = io.BytesIO(self._INSTANT_CONTENT)
        with unittest.mock.patch.object(
            api_client._api,
            "upload_file_init",
            return_value={"reuse": 0},
        ):
            with pytest.raises(InstantUploadNotAvailableError):
                api_client.file.upload(path, file, instant_only=True)

    def test_small_file_skips_instant_upload(self, api_client, root_dir):
        with unittest.mock.patch.object(
            api_client._api, "upload_file_init"
        ) as mock_init:
            upload_file(api_client, root_dir.path, size=64)
        mock_init.assert_not_called()

    def test_fallback(self, api_client, root_dir):
        path = self._upload_path(root_dir)
        file = io.BytesIO(self._MINIMUN_INSTANT_CONTENT)
        with unittest.mock.patch.object(
            api_client._api,
            "upload_file_init",
            return_value={"reuse": 0},
        ):
            result = api_client.file.upload(path, file)
        assert isinstance(result, File)
        assert result.sha1.upper() == self._MINIMUM_INSTANT_SHA1

        info = api_client.file.id(result.id)
        assert info.sha1.upper() == self._MINIMUM_INSTANT_SHA1

        # exception
        path = self._upload_path(root_dir)
        file = io.BytesIO(self._MINIMUN_INSTANT_CONTENT)
        err_msg = "simulated instant upload failure"
        with (
            unittest.mock.patch.object(
                api_client._api,
                "upload_file_init",
                side_effect=RuntimeError(err_msg),
            ),
            warnings.catch_warnings(record=True) as caught,
        ):
            warnings.simplefilter("always")
            result = api_client.file.upload(path, file)
        assert isinstance(result, File)
        assert result.sha1.upper() == self._MINIMUM_INSTANT_SHA1
        assert any("Instant upload failed" in str(w.message) for w in caught)
        assert any(err_msg in str(w.message) for w in caught)
