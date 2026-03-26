import hashlib
import unittest
from unittest.mock import MagicMock, patch

from cli115.client import File
from cli115.client.base import DownloadInfo, FileClient, RemoteFile
from tests.base import BaseTestCase


def _make_info(**kwargs):
    defaults = dict(
        url="https://example.com/file.bin",
        file_name="file.bin",
        file_size=1024,
        sha1="A" * 40,
        user_agent="TestAgent/1.0",
        referer="https://115.com/",
        cookies="UID=test",
    )
    defaults.update(kwargs)
    return DownloadInfo(**defaults)


class TestRemoteFile(unittest.TestCase):
    def test_properties(self):
        info = _make_info()
        rf = RemoteFile(info)
        self.assertEqual(rf.name, "file.bin")
        self.assertEqual(rf.size, 1024)
        self.assertTrue(rf.readable())
        self.assertFalse(rf.writable())
        self.assertTrue(rf.seekable())
        self.assertEqual(rf.tell(), 0)

    def test_stream_flag_defaults_false(self):
        rf = RemoteFile(_make_info())
        self.assertFalse(rf._stream)

    def test_set_stream_enables_and_disables(self):
        rf = RemoteFile(_make_info())
        rf.set_stream(True)
        self.assertTrue(rf._stream)
        rf.set_stream(False)
        self.assertFalse(rf._stream)

    def test_seek(self):
        rf = RemoteFile(_make_info(file_size=100))
        self.assertEqual(rf.seek(50), 50)
        self.assertEqual(rf.tell(), 50)
        self.assertEqual(rf.seek(10, 1), 60)
        self.assertEqual(rf.seek(-10, 2), 90)

    def test_read_eof_returns_empty(self):
        rf = RemoteFile(_make_info(file_size=5))
        rf.seek(5)
        self.assertEqual(rf.read(), b"")

    def test_context_manager(self):
        rf = RemoteFile(_make_info())
        with rf as f:
            self.assertIs(f, rf)

    def test_read_uses_range_header(self):
        info = _make_info(file_size=10)
        rf = RemoteFile(info)
        mock_resp = MagicMock()
        mock_resp.content = b"helloworld"
        with patch("httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.get.return_value = mock_resp
            data = rf.read()
        self.assertEqual(data, b"helloworld")
        mock_client.get.assert_called_once_with(
            info.url, headers={"Range": "bytes=0-9"}
        )

    def test_read_partial_uses_range_header(self):
        info = _make_info(file_size=10)
        rf = RemoteFile(info)
        mock_resp = MagicMock()
        mock_resp.content = b"hello"
        with patch("httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.get.return_value = mock_resp
            data = rf.read(5)
        self.assertEqual(data, b"hello")
        mock_client.get.assert_called_once_with(
            info.url, headers={"Range": "bytes=0-4"}
        )

    def test_read_stream_mode_uses_iter_bytes(self):
        info = _make_info(file_size=11)
        rf = RemoteFile(info)
        rf.set_stream(True)
        mock_resp = MagicMock()
        mock_resp.iter_bytes.return_value = iter([b"hello world"])
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_resp
        mock_ctx.__exit__.return_value = False
        with patch("httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.stream.return_value = mock_ctx
            data = rf.read()
        self.assertEqual(data, b"hello world")
        mock_client.stream.assert_called_once_with("GET", info.url)
        mock_resp.iter_bytes.assert_called_once_with(None)

    def test_read_stream_mode_partial(self):
        info = _make_info(file_size=11)
        rf = RemoteFile(info)
        rf.set_stream(True)
        mock_resp = MagicMock()
        mock_resp.iter_bytes.return_value = iter([b"hello", b" world"])
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_resp
        mock_ctx.__exit__.return_value = False
        with patch("httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.stream.return_value = mock_ctx
            data = rf.read(5)
        self.assertEqual(data, b"hello")
        mock_resp.iter_bytes.assert_called_once_with(5)

    def test_close_cleans_up_stream_and_client(self):
        info = _make_info(file_size=5)
        rf = RemoteFile(info)
        rf.set_stream(True)
        mock_resp = MagicMock()
        mock_resp.iter_bytes.return_value = iter([b"x"])
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_resp
        mock_ctx.__exit__.return_value = False
        with patch("httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.stream.return_value = mock_ctx
            rf.read(1)
            rf.close()
        mock_ctx.__exit__.assert_called_once_with(None, None, None)
        mock_client.close.assert_called_once()


class TestFileClientOpen(unittest.TestCase):
    def test_open_returns_remote_file_with_correct_info(self):
        info = _make_info()
        mock_self = MagicMock()
        mock_self.download_info.return_value = info
        rf = FileClient.open(mock_self, "/some/path")
        self.assertIsInstance(rf, RemoteFile)
        self.assertEqual(rf.name, info.file_name)
        self.assertEqual(rf.size, info.file_size)
        mock_self.download_info.assert_called_once_with("/some/path")

    def test_open_with_file_object(self):
        info = _make_info(file_name="test.mkv", file_size=2048)
        mock_self = MagicMock()
        mock_self.download_info.return_value = info
        mock_file = MagicMock()
        rf = FileClient.open(mock_self, mock_file)
        self.assertIsInstance(rf, RemoteFile)
        self.assertEqual(rf.name, "test.mkv")
        self.assertEqual(rf.size, 2048)
        mock_self.download_info.assert_called_once_with(mock_file)


class TestOpen(BaseTestCase):

    _entry: File

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        entry, _ = cls.upload_file(size=4096)
        cls._entry = entry

    def test_open_read_full_content(self):
        with self.client.file.open(self._entry) as rf:
            data = rf.read()
        sha1 = hashlib.sha1(data).hexdigest().upper()
        self.assertEqual(sha1, self._entry.sha1)
        self.assertEqual(len(data), self._entry.size)

        # partial read
        with self.client.file.open(self._entry) as rf:
            # Read first 100 bytes
            chunk1 = rf.read(100)
            self.assertEqual(len(chunk1), 100)
            self.assertEqual(rf.tell(), 100)

            # Read next 200 bytes
            chunk2 = rf.read(200)
            self.assertEqual(len(chunk2), 200)
            self.assertEqual(rf.tell(), 300)

        self.assertEqual(data[:100], chunk1)
        self.assertEqual(data[100:300], chunk2)

    def test_open_seekable_readable(self):
        with self.client.file.open(self._entry.path) as rf:
            self.assertEqual(rf.name, self._entry.name)
            self.assertTrue(rf.seekable())
            self.assertTrue(rf.readable())
            self.assertFalse(rf.writable())


if __name__ == "__main__":
    unittest.main()
