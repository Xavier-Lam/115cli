from unittest.mock import MagicMock, patch

from cli115.client.base import DownloadUrl, FileClient, RemoteFile


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
    return DownloadUrl(**defaults)


class TestRemoteFile:
    def test_properties(self):
        info = _make_info()
        rf = RemoteFile(info)
        assert rf.name == "file.bin"
        assert rf.size == 1024
        assert rf.readable()
        assert not rf.writable()
        assert rf.seekable()
        assert rf.tell() == 0

    def test_stream_flag_defaults_false(self):
        rf = RemoteFile(_make_info())
        assert not rf._stream

    def test_set_stream_enables_and_disables(self):
        rf = RemoteFile(_make_info())
        rf.set_stream(True)
        assert rf._stream
        rf.set_stream(False)
        assert not rf._stream

    def test_seek(self):
        rf = RemoteFile(_make_info(file_size=100))
        assert rf.seek(50) == 50
        assert rf.tell() == 50
        assert rf.seek(10, 1) == 60
        assert rf.seek(-10, 2) == 90

    def test_read_eof_returns_empty(self):
        rf = RemoteFile(_make_info(file_size=5))
        rf.seek(5)
        assert rf.read() == b""

    def test_context_manager(self):
        rf = RemoteFile(_make_info())
        with rf as f:
            assert f is rf

    def test_read_uses_range_header(self):
        info = _make_info(file_size=10)
        rf = RemoteFile(info)
        mock_resp = MagicMock()
        mock_resp.content = b"helloworld"
        with patch("httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.get.return_value = mock_resp
            data = rf.read()
        assert data == b"helloworld"
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
        assert data == b"hello"
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
        assert data == b"hello world"
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
        assert data == b"hello"
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


class TestFileClientOpen:
    def test_open_returns_remote_file_with_correct_info(self):
        info = _make_info()
        mock_self = MagicMock()
        mock_self.url.return_value = info
        rf = FileClient.open(mock_self, "/some/path")
        assert isinstance(rf, RemoteFile)
        assert rf.name == info.file_name
        assert rf.size == info.file_size
        mock_self.url.assert_called_once_with("/some/path")

    def test_open_with_file_object(self):
        info = _make_info(file_name="test.mkv", file_size=2048)
        mock_self = MagicMock()
        mock_self.url.return_value = info
        mock_file = MagicMock()
        rf = FileClient.open(mock_self, mock_file)
        assert isinstance(rf, RemoteFile)
        assert rf.name == "test.mkv"
        assert rf.size == 2048
        mock_self.url.assert_called_once_with(mock_file)
