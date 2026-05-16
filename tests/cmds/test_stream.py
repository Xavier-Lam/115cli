from contextlib import contextmanager
from datetime import datetime
import threading
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
import urllib.request
from wsgiref.simple_server import make_server, WSGIRequestHandler

import m3u8
import pytest

from cli115.client.models import AccountInfo, File
from cli115.cmds.stream import _ThreadingWSGIServer, StreamApp
from cli115.exceptions import CommandLineError
from tests.helpers import make_parser

_MASTER_M3U8_VARIANT = (
    "#EXTM3U\n"
    "#EXT-X-STREAM-INF:BANDWIDTH=1200000,RESOLUTION=1280x720\n"
    "https://stream.115.com/hls/abc/HD/index.m3u8?token=t1\n"
    "#EXT-X-STREAM-INF:BANDWIDTH=600000,RESOLUTION=854x480\n"
    "https://stream.115.com/hls/abc/SD/index.m3u8?token=t1\n"
)

_QUALITY_M3U8 = (
    "#EXTM3U\n"
    "#EXT-X-TARGETDURATION:10\n"
    "#EXTINF:9.009,\n"
    "https://ts.115.com/seg1.ts\n"
    "#EXT-X-ENDLIST\n"
)


@contextmanager
def _start_test_server(app):
    httpd = make_server("127.0.0.1", 0, app, _ThreadingWSGIServer, WSGIRequestHandler)
    port = httpd.server_address[1]
    t = threading.Thread(
        target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    t.start()
    try:
        yield port
    finally:
        httpd.shutdown()
        t.join(timeout=2)


def _make_file(pickcode="abc123"):
    return File(
        id="200",
        parent_id="100",
        name="video.mp4",
        path="/video.mp4",
        pickcode=pickcode,
        created_time=datetime(2025, 1, 1),
        modified_time=datetime(2025, 6, 1),
        open_time=None,
        size=1024,
        sha1="a" * 40,
        file_type="mp4",
        starred=False,
    )


class TestStreamApp:
    def test_serve_main_m3u8(self):
        app = StreamApp(
            base_url="http://127.0.0.1",
            master=m3u8.loads(_MASTER_M3U8_VARIANT),
            api=MagicMock(),
        )
        with _start_test_server(app) as port:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/main.m3u8")
            assert resp.status == 200
            ct = resp.headers.get("Content-Type", "")
            assert "mpegurl" in ct.lower()
            body = resp.read().decode("utf-8")
            assert "#EXTM3U" in body

    def test_serve_quality_m3u8(self):
        mock_api = MagicMock()
        mock_api.get.return_value.content = _QUALITY_M3U8.encode()
        mock_api.get.return_value.status_code = 200
        mock_api.get.return_value.headers = {}
        app = StreamApp(
            base_url="http://127.0.0.1",
            master=m3u8.loads(_MASTER_M3U8_VARIANT),
            api=mock_api,
        )
        with _start_test_server(app) as port:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/1200000.m3u8")
            assert resp.status == 200
            body = resp.read().decode("utf-8")
            assert "#EXTM3U" in body
            # segment should be rewritten to local proxy path
            assert "/segments/" in body
            assert "ts.115.com/seg1.ts" in body

    def test_serve_segment(self):
        mock_api = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {}
        mock_resp.iter_bytes.return_value = iter([b"fake-ts-content"])
        mock_api.stream.return_value.__enter__.return_value = mock_resp
        mock_api.stream.return_value.__exit__.return_value = False

        app = StreamApp(
            base_url="http://127.0.0.1",
            master=m3u8.loads(_MASTER_M3U8_VARIANT),
            api=mock_api,
        )
        seg_key = "ts.115.com/seg1.ts"
        app._segment_map[seg_key] = "https://ts.115.com/seg1.ts"

        with _start_test_server(app) as port:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/segments/{seg_key}")
            assert resp.status == 200
            assert resp.read() == b"fake-ts-content"
            assert app._stats["read_bytes"] == len(b"fake-ts-content")

    def test_unknown_quality_returns_404(self):
        app = StreamApp(
            base_url="http://127.0.0.1",
            master=m3u8.loads(_MASTER_M3U8_VARIANT),
            api=MagicMock(),
        )
        with _start_test_server(app) as port:
            with pytest.raises(HTTPError) as exc_info:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/unknownquality.m3u8")
            assert exc_info.value.code == 404

    def test_unknown_segment_returns_404(self):
        app = StreamApp(
            base_url="http://127.0.0.1",
            master=m3u8.loads(_MASTER_M3U8_VARIANT),
            api=MagicMock(),
        )
        with _start_test_server(app) as port:
            with pytest.raises(HTTPError) as exc_info:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/segments/nonexistent/path.ts"
                )
            assert exc_info.value.code == 404


class TestStreamCommand:
    @patch("cli115.cmds.stream.make_server")
    @patch("cli115.cmds.stream.StreamCommand._create_client")
    def test_variant_stream_prints_urls(self, mock_create, mock_make_server, capsys):
        mock_client = MagicMock()
        mock_client.file.stat.return_value = _make_file("abc123")

        mock_client.stream.info.return_value = {"video_url": "https://hls.115.com/play"}
        mock_client.stream.get_m3u8.return_value = m3u8.loads(_MASTER_M3U8_VARIANT)
        mock_create.return_value = mock_client

        mock_httpd = MagicMock()
        mock_make_server.return_value = mock_httpd
        mock_httpd.serve_forever.side_effect = KeyboardInterrupt

        parser, commands = make_parser()
        args = parser.parse_args(["stream", "/video.mp4"])
        commands["stream"].execute(args)

        out = capsys.readouterr()
        assert "http://127.0.0.1:20115/main.m3u8" in out.out
        assert "1200000.m3u8" in out.out
        assert "1280x720" in out.out
        assert "1.2 Mbps" in out.out
        assert "600000.m3u8" in out.out
        assert "854x480" in out.out
        assert "CTRL+C" in out.out
        assert "not protected" in out.err
        assert "Total bytes read" in out.out

    @patch("cli115.cmds.stream.make_server")
    @patch("cli115.cmds.stream.StreamCommand._create_client")
    def test_stream_by_id(self, mock_create, mock_make_server, capsys):
        mock_client = MagicMock()
        mock_client.file.id.return_value = _make_file("abc123")

        mock_client.stream.info.return_value = {"video_url": "https://hls.115.com/play"}
        mock_client.stream.get_m3u8.return_value = m3u8.loads(_MASTER_M3U8_VARIANT)
        mock_create.return_value = mock_client

        mock_httpd = MagicMock()
        mock_make_server.return_value = mock_httpd
        mock_httpd.serve_forever.side_effect = KeyboardInterrupt

        parser, commands = make_parser()
        args = parser.parse_args(["stream", "--id", "3426493810175165487"])
        commands["stream"].execute(args)

        mock_client.file.id.assert_called_once_with("3426493810175165487")
        out = capsys.readouterr()
        assert "http://127.0.0.1:20115/main.m3u8" in out.out

    @patch("cli115.cmds.stream.make_server")
    @patch("cli115.cmds.stream.StreamCommand._create_client")
    def test_custom_port_and_host(self, mock_create, mock_make_server, capsys):
        mock_client = MagicMock()
        mock_client.file.stat.return_value = _make_file("abc123")

        mock_client.stream.info.return_value = {"video_url": "https://hls.115.com/play"}
        mock_client.stream.get_m3u8.return_value = m3u8.loads(_MASTER_M3U8_VARIANT)
        mock_create.return_value = mock_client

        mock_httpd = MagicMock()
        mock_make_server.return_value = mock_httpd
        mock_httpd.serve_forever.side_effect = KeyboardInterrupt

        parser, commands = make_parser()
        args = parser.parse_args(
            ["stream", "/video.mp4", "-p", "8080", "--host", "0.0.0.0"]
        )
        commands["stream"].execute(args)

        call_host, call_port = mock_make_server.call_args[0][:2]
        assert call_host == "0.0.0.0"
        assert call_port == 8080
        out = capsys.readouterr()
        assert "http://0.0.0.0:8080/main.m3u8" in out.out

    @patch("cli115.cmds.stream.StreamCommand._create_client")
    def test_queue_shows_count_and_time(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_client.file.stat.return_value = _make_file("abc123")
        mock_client.stream.info.return_value = {
            "queue_url": "https://transcode.115.com/check",
            "sha1": "a" * 40,
            "file_id": "200",
        }
        mock_client.stream.transcode_status.return_value = {
            "result": 0,
            "status": 1,
            "count": 1016,
            "time": 1795,
            "priority": 1,
        }
        mock_client.account.info.return_value = AccountInfo(
            user_name="user", user_id=1, vip=False, expire=None
        )
        mock_create.return_value = mock_client

        parser, commands = make_parser()
        args = parser.parse_args(["stream", "/video.mp4"])
        with pytest.raises(CommandLineError):
            commands["stream"].execute(args)

        out = capsys.readouterr().out
        assert "1016" in out
        assert "29m" in out

    @patch("cli115.cmds.stream.StreamCommand._create_client")
    def test_vip_auto_accelerates(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_client.file.stat.return_value = _make_file("abc123")
        mock_client.stream.info.return_value = {
            "queue_url": "https://transcode.115.com/check",
            "sha1": "a" * 40,
            "file_id": "200",
        }
        mock_client.stream.transcode_status.return_value = {
            "result": 0,
            "status": 1,
            "count": 50,
            "time": 300,
            "priority": 1,
        }
        mock_client.account.info.return_value = AccountInfo(
            user_name="vipuser", user_id=2, vip=True, expire=None
        )
        mock_create.return_value = mock_client

        parser, commands = make_parser()
        args = parser.parse_args(["stream", "/video.mp4"])
        with pytest.raises(CommandLineError):
            commands["stream"].execute(args)

        mock_client.stream.accelerate_transcode.assert_called_once()
        out = capsys.readouterr().out
        assert "VIP acceleration applied" in out

    @patch("cli115.cmds.stream.StreamCommand._create_client")
    def test_already_accelerated_skips_boost(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_client.file.stat.return_value = _make_file("abc123")
        mock_client.stream.info.return_value = {
            "queue_url": "https://transcode.115.com/check",
            "sha1": "a" * 40,
            "file_id": "200",
        }
        mock_client.stream.transcode_status.return_value = {
            "result": 0,
            "status": 3,
            "count": 0,
            "time": 120,
            "priority": 2,
        }
        mock_client.account.info.return_value = AccountInfo(
            user_name="vipuser", user_id=2, vip=True, expire=None
        )
        mock_create.return_value = mock_client

        parser, commands = make_parser()
        args = parser.parse_args(["stream", "/video.mp4"])
        with pytest.raises(CommandLineError):
            commands["stream"].execute(args)

        mock_client.stream.accelerate_transcode.assert_not_called()
        out = capsys.readouterr().out
        assert "already active" in out

    @patch("cli115.cmds.stream.StreamCommand._create_client")
    def test_non_vip_does_not_accelerate(self, mock_create):
        mock_client = MagicMock()
        mock_client.file.stat.return_value = _make_file("abc123")
        mock_client.stream.info.return_value = {
            "queue_url": "https://transcode.115.com/check",
            "sha1": "a" * 40,
            "file_id": "200",
        }
        mock_client.stream.transcode_status.return_value = {
            "result": 0,
            "status": 1,
            "count": 100,
            "time": 600,
            "priority": 1,
        }
        mock_client.account.info.return_value = AccountInfo(
            user_name="freeuser", user_id=3, vip=False, expire=None
        )
        mock_create.return_value = mock_client

        parser, commands = make_parser()
        args = parser.parse_args(["stream", "/video.mp4"])
        with pytest.raises(CommandLineError):
            commands["stream"].execute(args)

        mock_client.stream.accelerate_transcode.assert_not_called()


class TestTranscodeCommand:
    @patch("cli115.cmds.transcode.TranscodeCommand._create_client")
    def test_already_available(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_client.file.stat.return_value = _make_file("abc123")
        mock_client.stream.info.return_value = {"video_url": "https://hls.115.com/play"}
        mock_create.return_value = mock_client

        parser, commands = make_parser()
        args = parser.parse_args(["transcode", "/video.mp4"])
        commands["transcode"].execute(args)

        out = capsys.readouterr().out
        assert "already available for streaming" in out
        mock_client.stream.transcode_status.assert_not_called()

    @patch("cli115.cmds.transcode.TranscodeCommand._create_client")
    def test_by_id(self, mock_create):
        mock_client = MagicMock()
        mock_client.file.id.return_value = _make_file("abc123")
        mock_client.stream.info.return_value = {"video_url": "https://hls.115.com/play"}
        mock_create.return_value = mock_client

        parser, commands = make_parser()
        args = parser.parse_args(["transcode", "--id", "3426493810175165487"])
        commands["transcode"].execute(args)

        mock_client.file.id.assert_called_once_with("3426493810175165487")

    @patch("cli115.cmds.transcode.TranscodeCommand._create_client")
    def test_invalid_video_raises(self, mock_create):
        mock_client = MagicMock()
        mock_client.file.stat.return_value = _make_file("abc123")
        mock_client.stream.info.return_value = {}
        mock_create.return_value = mock_client

        parser, commands = make_parser()
        args = parser.parse_args(["transcode", "/video.mp4"])
        with pytest.raises(CommandLineError, match="not available"):
            commands["transcode"].execute(args)

    @patch("cli115.cmds.transcode.TranscodeCommand._create_client")
    def test_queue_shows_count_and_time(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_client.file.stat.return_value = _make_file("abc123")
        mock_client.stream.info.return_value = {
            "queue_url": "https://transcode.115.com/check",
            "sha1": "a" * 40,
            "file_id": "200",
        }
        mock_client.stream.transcode_status.return_value = {
            "result": 0,
            "status": 1,
            "count": 1016,
            "time": 1795,
            "priority": 1,
        }
        mock_client.account.info.return_value = AccountInfo(
            user_name="user", user_id=1, vip=False, expire=None
        )
        mock_create.return_value = mock_client

        parser, commands = make_parser()
        args = parser.parse_args(["transcode", "/video.mp4"])
        commands["transcode"].execute(args)

        out = capsys.readouterr().out
        assert "1016" in out
        assert "29m" in out

    @patch("cli115.cmds.transcode.TranscodeCommand._create_client")
    def test_vip_auto_accelerates(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_client.file.stat.return_value = _make_file("abc123")
        mock_client.stream.info.return_value = {
            "queue_url": "https://transcode.115.com/check",
            "sha1": "a" * 40,
            "file_id": "200",
        }
        mock_client.stream.transcode_status.return_value = {
            "result": 0,
            "status": 1,
            "count": 50,
            "time": 300,
            "priority": 1,
        }
        mock_client.account.info.return_value = AccountInfo(
            user_name="vipuser", user_id=2, vip=True, expire=None
        )
        mock_create.return_value = mock_client

        parser, commands = make_parser()
        args = parser.parse_args(["transcode", "/video.mp4"])
        commands["transcode"].execute(args)

        mock_client.stream.accelerate_transcode.assert_called_once()
        out = capsys.readouterr().out
        assert "VIP acceleration applied" in out

    @patch("cli115.cmds.transcode.TranscodeCommand._create_client")
    def test_already_accelerated_skips_boost(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_client.file.stat.return_value = _make_file("abc123")
        mock_client.stream.info.return_value = {
            "queue_url": "https://transcode.115.com/check",
            "sha1": "a" * 40,
            "file_id": "200",
        }
        mock_client.stream.transcode_status.return_value = {
            "result": 0,
            "status": 3,
            "count": 0,
            "time": 120,
            "priority": 2,
        }
        mock_client.account.info.return_value = AccountInfo(
            user_name="vipuser", user_id=2, vip=True, expire=None
        )
        mock_create.return_value = mock_client

        parser, commands = make_parser()
        args = parser.parse_args(["transcode", "/video.mp4"])
        commands["transcode"].execute(args)

        mock_client.stream.accelerate_transcode.assert_not_called()
        out = capsys.readouterr().out
        assert "already active" in out

    @patch("cli115.cmds.transcode.TranscodeCommand._create_client")
    def test_non_vip_does_not_accelerate(self, mock_create):
        mock_client = MagicMock()
        mock_client.file.stat.return_value = _make_file("abc123")
        mock_client.stream.info.return_value = {
            "queue_url": "https://transcode.115.com/check",
            "sha1": "a" * 40,
            "file_id": "200",
        }
        mock_client.stream.transcode_status.return_value = {
            "result": 0,
            "status": 1,
            "count": 100,
            "time": 600,
            "priority": 1,
        }
        mock_client.account.info.return_value = AccountInfo(
            user_name="freeuser", user_id=3, vip=False, expire=None
        )
        mock_create.return_value = mock_client

        parser, commands = make_parser()
        args = parser.parse_args(["transcode", "/video.mp4"])
        commands["transcode"].execute(args)

        mock_client.stream.accelerate_transcode.assert_not_called()
