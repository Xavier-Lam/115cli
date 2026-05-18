"""Stream command – starts a local HLS proxy for 115 video streams."""

from __future__ import annotations

import argparse
import secrets
import threading
from socketserver import ThreadingMixIn
from urllib.parse import quote, urlparse
from wsgiref.simple_server import make_server, WSGIRequestHandler, WSGIServer

import bottle
import httpx
import m3u8

from cli115.cmds.transcode import TranscodeCommand
from cli115.exceptions import CommandLineError
from cli115.helpers import format_size


class StreamCommand(TranscodeCommand):
    """Stream a 115 video file via a local HLS proxy server."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
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
        parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="Enable verbose logging for the proxy server",
        )
        key_group = parser.add_mutually_exclusive_group()
        key_group.add_argument(
            "-k",
            "--key",
            default=None,
            metavar="KEY",
            help="Set a custom access key",
        )
        key_group.add_argument(
            "--no-key",
            action="store_true",
            help="Disable key-based access protection",
        )

    def execute(self, args: argparse.Namespace) -> None:
        client = self._create_client()
        entry = self._get_entry(args, client)
        if not self._is_available(client, entry):
            try:
                self._transcode(client, entry)
            except Exception as e:
                self.warn(f"an error occurred while checking transcode status: {e}")
            raise CommandLineError(
                "video is still being processed, please try again later"
            )

        master = client.stream.get_m3u8(entry.pickcode)
        if not master.is_variant:
            raise NotImplementedError("non-variant playlists are not supported")

        host = args.host
        port = args.port
        base_url = f"http://{host}:{port}"

        if args.no_key:
            access_key = ""
        elif args.key:
            access_key = args.key
        else:
            access_key = secrets.token_urlsafe(16)

        app = StreamApp(
            master=master,
            api=client.stream._api,
            access_key=access_key,
        )

        print(f"\nStream: {base_url}/main.m3u8{app.qs}")
        for playlist in master.playlists:
            si = playlist.stream_info
            res = f"{si.resolution[0]}x{si.resolution[1]}"
            bw = _format_bandwidth(si.bandwidth)
            print(f"  [{res}, {bw}] {base_url}/{si.bandwidth}.m3u8{app.qs}")
        print("\nPress CTRL+C to stop the proxy server.")

        class _Handler(WSGIRequestHandler):
            if not args.verbose:

                def log_message(self, *args, **kwargs) -> None:
                    pass

        httpd = make_server(host, port, app, _ThreadingWSGIServer, _Handler)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        print(f"\nTotal bytes read: {format_size(app._stats['read_bytes'])}")


class StreamApp(bottle.Bottle):
    """WSGI application for the local HLS proxy server."""

    _proxy_headers = (
        "content-type",
        "content-length",
    )

    def __init__(
        self,
        master: m3u8.M3U8,
        api: httpx.Client,
        access_key: str = "",
    ) -> None:
        super().__init__()
        self._access_key = access_key
        self._m3u8_map = {
            str(playlist.stream_info.bandwidth): playlist.absolute_uri
            for playlist in master.playlists
        }
        self._master = master
        self._api = api
        self._segment_map = {}
        self._segment_lock = threading.Lock()
        self._stats = {"read_bytes": 0}
        self.init()

    @property
    def qs(self) -> str:
        return f"?key={quote(self._access_key)}" if self._access_key else ""

    def init(self):
        def check_key(callback):
            def wrapper(*args, **kwargs):
                if (
                    self._access_key
                    and bottle.request.query.get("key") != self._access_key
                ):
                    bottle.abort(403, "invalid or missing key")
                return callback(*args, **kwargs)

            return wrapper

        self.route("/main.m3u8", callback=check_key(self._serve_master))
        self.route("/<name>.m3u8", callback=check_key(self._serve_quality))
        self.route("/segments/<path:path>", callback=check_key(self._serve_segment))

    def _serve_master(self) -> str:
        bottle.response.content_type = "application/vnd.apple.mpegurl"
        with self._segment_lock:
            for playlist in self._master.playlists:
                bandwidth = playlist.stream_info.bandwidth
                playlist.uri = f"{self.base_url}/{bandwidth}.m3u8{self.qs}"
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
            seg_key = parsed_url.hostname + parsed_url.path
            with self._segment_lock:
                self._segment_map[seg_key] = seg.absolute_uri
            seg.uri = f"{self.base_url}/segments/{seg_key}{self.qs}"

        for header, value in resp.headers.items():
            if header.lower() in self._proxy_headers:
                bottle.response.set_header(header, value)

        return parsed.dumps()

    def _serve_segment(self, path: str):
        orig_url = self._segment_map.get(path)
        if orig_url is None:
            bottle.abort(404, "unknown segment")

        return self._proxy(orig_url)

    @property
    def base_url(self) -> str:
        req = bottle.request
        scheme = req.get_header("X-Forwarded-Proto") or req.urlparts.scheme
        host = (
            req.get_header("X-Forwarded-Host")
            or req.get_header("Host")
            or req.urlparts.netloc
        )
        return f"{scheme}://{host}"

    def _proxy(self, url):
        def _gen():
            with self._api.stream("GET", url) as resp:
                bottle.response.status = resp.status_code
                for header, value in resp.headers.items():
                    if header.lower() in self._proxy_headers:
                        bottle.response.set_header(header, value)
                for chunk in resp.iter_bytes(chunk_size=65536):
                    with self._segment_lock:
                        self._stats["read_bytes"] += len(chunk)
                    yield chunk

        return _gen()


class _ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def _format_bandwidth(bw: int) -> str:
    if bw >= 1_000_000:
        return f"{bw / 1_000_000:.1f} Mbps"
    return f"{bw // 1000} Kbps"
