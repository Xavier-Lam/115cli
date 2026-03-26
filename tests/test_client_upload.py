import hashlib
import io
import unittest
import unittest.mock
import uuid
import warnings

from cli115.client import File, webapi
from cli115.exceptions import AlreadyExistsError, InstantUploadNotAvailableError
from tests.base import TEST_ROOT, BaseTestCase


class TestUpload(BaseTestCase):

    def test_upload_file_with_hash(self):
        entry, expected_sha1 = self.upload_file(size=1024)
        self.assertIsInstance(entry, File)
        self.assertEqual(len(entry.sha1), 40)
        self.assertEqual(entry.sha1, expected_sha1)
        self.assertEqual(entry.size, 1024)

    def test_upload_file_like_object(self):
        content = uuid.uuid4().bytes * 64
        expected_sha1 = hashlib.sha1(content).hexdigest().upper()
        buf = io.BytesIO(content)
        buf.name = f"up_buf_{uuid.uuid4().hex[:8]}.bin"
        result = self.client.file.upload(f"{TEST_ROOT}/{buf.name}", buf)
        self.assertIsInstance(result, File)
        self.assertEqual(result.sha1, expected_sha1)

    def test_upload_file_already_exists(self):
        entry, _ = self.upload_file(size=512)
        with self.assertRaises(AlreadyExistsError):
            self.client.file.upload(entry.path, io.BytesIO(b"new content"))


class TestInstantUpload(BaseTestCase):

    # "a" * 4096 * 1024 is eligible for instant upload.
    _INSTANT_CONTENT = b"a" * 4096 * 1024
    _INSTANT_SHA1 = hashlib.sha1(_INSTANT_CONTENT).hexdigest().upper()
    _MINIMUN_INSTANT_CONTENT = b"a" * 64 * 1024
    _MINIMUM_INSTANT_SHA1 = hashlib.sha1(_MINIMUN_INSTANT_CONTENT).hexdigest().upper()
    _ORIGINAL_MIN_INSTANT_SIZE = webapi.MIN_INSTANT_UPLOAD_SIZE

    def setUp(self):
        super().setUp()
        webapi.MIN_INSTANT_UPLOAD_SIZE = 64 * 1024

    def tearDown(self):
        webapi.MIN_INSTANT_UPLOAD_SIZE = self._ORIGINAL_MIN_INSTANT_SIZE
        super().tearDown()

    def _upload_path(self) -> str:
        fname = f"instant_{uuid.uuid4().hex[:8]}.bin"
        return f"{TEST_ROOT}/{fname}"

    def test_instant_upload_success(self):
        path = self._upload_path()
        file = io.BytesIO(self._INSTANT_CONTENT)
        with (
            unittest.mock.patch.object(
                self.client._api, "upload_file_sample"
            ) as mock_sample,
        ):
            result = self.client.file.upload(path, file)
        self.assertIsInstance(result, File)
        self.assertEqual(result.sha1, self._INSTANT_SHA1)
        mock_sample.assert_not_called()

        info = self.client.file.id(result.id)
        self.assertEqual(info.sha1, self._INSTANT_SHA1)

    def test_instant_only_raises_when_not_available(self):
        path = self._upload_path()
        file = io.BytesIO(self._INSTANT_CONTENT)
        with (
            unittest.mock.patch.object(
                self.client._api,
                "upload_file_init",
                return_value={"reuse": 0},
            ),
        ):
            with self.assertRaises(InstantUploadNotAvailableError):
                self.client.file.upload(path, file, instant_only=True)

    def test_below_threshold_skips_instant_upload(self):
        with unittest.mock.patch.object(
            self.client._api, "upload_file_init"
        ) as mock_init:
            self.upload_file(TEST_ROOT, size=64)
        mock_init.assert_not_called()

    def test_fallback_to_normal_upload(self):
        path = self._upload_path()
        file = io.BytesIO(self._MINIMUN_INSTANT_CONTENT)
        with (
            unittest.mock.patch.object(
                self.client._api,
                "upload_file_init",
                return_value={"reuse": 0},
            ),
        ):
            result = self.client.file.upload(path, file)
        self.assertIsInstance(result, File)
        self.assertEqual(result.sha1.upper(), self._MINIMUM_INSTANT_SHA1)

        info = self.client.file.id(result.id)
        self.assertEqual(info.sha1.upper(), self._MINIMUM_INSTANT_SHA1)

    def test_instant_error_fallback_with_warning(self):
        path = self._upload_path()
        file = io.BytesIO(self._MINIMUN_INSTANT_CONTENT)
        with (
            unittest.mock.patch.object(
                self.client._api,
                "upload_file_init",
                side_effect=RuntimeError("simulated instant upload failure"),
            ),
            warnings.catch_warnings(record=True) as caught,
        ):
            warnings.simplefilter("always")
            result = self.client.file.upload(path, file)
        self.assertIsInstance(result, File)
        self.assertEqual(result.sha1.upper(), self._MINIMUM_INSTANT_SHA1)
        self.assertTrue(
            any("Instant upload failed" in str(w.message) for w in caught),
        )


if __name__ == "__main__":
    unittest.main()
