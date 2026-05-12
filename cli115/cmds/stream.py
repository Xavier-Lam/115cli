"""Stream command – starts a local HLS proxy for 115 video streams."""

from __future__ import annotations

import argparse
import sys
import threading
from socketserver import ThreadingMixIn
from urllib.parse import urlparse
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

import bottle
import httpx
import m3u8

from cli115.cmds.base import BaseCommand
from cli115.exceptions import CommandLineError


class StreamCommand(BaseCommand):
    """Stream a 115 video file via a local HLS proxy server."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
        parser.add_argument("path", nargs="?", help="Remote file path on 115")
        parser.add_argument(
            "--id",
            dest="file_id",
            default=None,
            help="Stream by remote file ID instead of path",
        )
        parser.add_argument(
            "-p",
            "--port",
            type=int,
            default=20115,
            help="Local port to listen on (default: 20115)",
        )
        parser.add_argument(
            "--host",
            default="127.0.0.1",
            help="Local host to bind to (default: 127.0.0.1)",
        )

    def execute(self, args: argparse.Namespace) -> None:
        if not args.file_id and not args.path:
            raise CommandLineError("either 'path' or '--id' is required")
        if args.file_id and args.path:
            raise CommandLineError("use either 'path' or '--id', not both")

        client = self._create_client()

        if args.path:
            entry = client.file.stat(args.path)
        else:
            entry = client.file.id(args.file_id)

        if entry.is_directory:
            raise CommandLineError(f"path is a directory: {entry.path or entry.id}")
        if not entry.pickcode:
            raise CommandLineError(f"file has no pickcode: {entry.path or entry.id}")

        host = args.host
        port = args.port
        base_url = f"http://{host}:{port}"

        master = client.stream.get_m3u8(entry.pickcode)
        if not master.is_variant:
            raise NotImplementedError("non-variant playlists are not supported")

        app = StreamApp(base_url=base_url, master=master, api=client.stream._api)

        print(
            "Warning: the stream proxy is not protected — anyone with access "
            "to this machine can connect to it.",
            file=sys.stderr,
        )
        print(f"\nStream: {base_url}/main.m3u8")
        for playlist in master.playlists:
            si = playlist.stream_info
            res = f"{si.resolution[0]}x{si.resolution[1]}"
            bw = _format_bandwidth(si.bandwidth)
            print(f"  [{res}, {bw}] {base_url}/{si.bandwidth}.m3u8")
        print("\nPress CTRL+C to stop the proxy server.")

        httpd = make_server(
            host, port, app, _ThreadingWSGIServer, _QuietWSGIRequestHandler
        )
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


class StreamApp(bottle.Bottle):
    """WSGI application for the local HLS proxy server."""

    _proxy_headers = (
        "content-type",
        "content-length",
    )

    def __init__(self, base_url: str, master: m3u8.M3U8, api: httpx.Client) -> None:
        super().__init__()
        self._base_url = base_url
        self._m3u8_map = {}
        for playlist in master.playlists:
            bandwidth = playlist.stream_info.bandwidth
            self._m3u8_map[str(bandwidth)] = playlist.absolute_uri
            playlist.uri = f"{base_url}/{bandwidth}.m3u8"
        self._master = master
        self._api = api
        self._segment_map = {}
        self._segment_lock = threading.Lock()
        self.init()

    def init(self):
        self.route("/main.m3u8", callback=self._serve_master)
        self.route("/<name>.m3u8", callback=self._serve_quality)
        self.route("/segments/<path:path>", callback=self._serve_segment)

    def _serve_master(self) -> str:
        bottle.response.content_type = "application/vnd.apple.mpegurl"
        return self._master.dumps()

    def _serve_quality(self, name: str) -> str:
        url = self._m3u8_map.get(name)
        if not url:
            bottle.abort(404, "unknown quality")

        resp = self._api.get(url)
        bottle.response.status = resp.status_code

        parsed = m3u8.loads(resp.content.decode("utf-8"), uri=url)
        for seg in parsed.segments:
            parsed_url = urlparse(seg.absolute_uri)
            key = parsed_url.hostname + parsed_url.path
            with self._segment_lock:
                self._segment_map[key] = seg.absolute_uri
            seg.uri = f"{self._base_url}/segments/{key}"

        for header, value in resp.headers.items():
            if header.lower() in self._proxy_headers:
                bottle.response.set_header(header, value)

        return parsed.dumps()

    def _serve_segment(self, path: str):
        orig_url = self._segment_map.get(path)
        if orig_url is None:
            bottle.abort(404, "unknown segment")

        return self._proxy(orig_url)

    def _proxy(self, url):
        def _gen():
            with self._api.stream("GET", url) as resp:
                bottle.response.status = resp.status_code
                for header, value in resp.headers.items():
                    if header.lower() in self._proxy_headers:
                        bottle.response.set_header(header, value)
                for chunk in resp.iter_bytes(chunk_size=65536):
                    yield chunk

        return _gen()


class _ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class _QuietWSGIRequestHandler(WSGIRequestHandler):
    def log_message(self, *args, **kwargs) -> None:
        pass

    def log_request(self, *args, **kwargs) -> None:
        pass


def _format_bandwidth(bw: int) -> str:
    if bw >= 1_000_000:
        return f"{bw / 1_000_000:.1f} Mbps"
    return f"{bw // 1000} Kbps"
