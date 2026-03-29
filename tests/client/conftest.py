import hashlib
import logging
import os
import tempfile
import time
import unittest.mock
import uuid
from functools import cached_property
from unittest.mock import MagicMock, patch

import httpcore
import httpcore_request
import pytest

from cli115.api.web import p115client
from cli115.auth import CookieAuth
from cli115.client import Client, Directory, File, create_client, webapi
from cli115.helpers import normalize_path, parse_cookie_string


TEST_ROOT = "/115cli_test"


def make_client():
    """Create a WebAPIClient with a fully mocked P115 API backend."""
    with patch("cli115.client.webapi.P115Client"):
        client = webapi.WebAPIClient(MagicMock())
    client._api = MagicMock()
    return client


def make_dir(name="dir", id="100", parent_id="0", path=None, file_count=0):
    return Directory(
        id=id,
        parent_id=parent_id,
        name=name,
        path=path if path is not None else f"/{name}",
        pickcode="",
        created_time=None,
        modified_time=None,
        open_time=None,
        file_count=file_count,
    )


def make_file(
    name="file.txt", id="200", parent_id="0", path=None, size=1024, sha1="ABC123"
):
    return File(
        id=id,
        parent_id=parent_id,
        name=name,
        path=path if path is not None else f"/{name}",
        pickcode="",
        created_time=None,
        modified_time=None,
        open_time=None,
        size=size,
        sha1=sha1,
        file_type="txt",
    )


class _LogCapture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records: list[str] = []

    def emit(self, record):
        self.records.append(self.format(record))


_log_capture = _LogCapture()
_log_capture.setFormatter(logging.Formatter("%(message)s"))


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    records = _log_capture.records
    if not records:
        return
    records115 = [r for r in records if ".115.com" in r.splitlines()[0]]
    terminalreporter.write_sep(
        "=",
        f"API requests: {len(records)} total, {len(records115)} to 115.com",
    )
    for msg in records115:
        for line in msg.splitlines():
            terminalreporter.write_line(f"  {line}")


def create_temp_file(content: bytes, name: str = "") -> str:
    if name:
        dirpath = tempfile.mkdtemp()
        path = os.path.join(dirpath, name)
        with open(path, "wb") as fh:
            fh.write(content)
        return path
    fd, path = tempfile.mkstemp()
    try:
        os.write(fd, content)
    finally:
        os.close(fd)
    return path


def upload_file(
    client: Client, dest_dir: str, *, fname: str = "", size: int = 64
) -> File:
    if not fname:
        fname = f"f_{uuid.uuid4().hex[:8]}.bin"
    content = os.urandom(size)
    sha1 = hashlib.sha1(content).hexdigest().upper()
    local = create_temp_file(content, name=fname)
    try:
        entry = client.file.upload(f"{dest_dir}/{fname}", local)
    finally:
        os.unlink(local)
        os.rmdir(os.path.dirname(local))
    assert entry.sha1.upper() == sha1
    return entry


def _patch_client_registry(client: Client) -> None:
    """Patch a client instance to support a test entry registry.

    Registered entries are returned directly from id/path lookups without
    making any API calls. Use client.register_entry(entry) to add an entry
    and client.unregister_entry(entry) to remove it.
    """
    _by_id: dict[str, Directory | File] = {}
    _by_path: dict[str, Directory | File] = {}

    def register_entry(entry: Directory | File) -> None:
        _by_id[entry.id] = entry
        _by_path[normalize_path(entry.path)] = entry

    def unregister_entry(entry: Directory | File) -> None:
        _by_id.pop(entry.id, None)
        _by_path.pop(normalize_path(entry.path), None)

    client.register_entry = register_entry
    client.unregister_entry = unregister_entry

    _orig_resolve_dir_id = client._resolve_dir_id
    _orig_file_id = client.file.id
    _orig_resolve_entry = client.file._resolve_entry

    def _resolve_dir_id_with_registry(path):
        if isinstance(path, Directory):
            return path.id
        if isinstance(path, str):
            key = normalize_path(path)
            if key in _by_path:
                return _by_path[key].id
        return _orig_resolve_dir_id(path)

    def _file_id_with_registry(file_id):
        if file_id in _by_id:
            return _by_id[file_id]
        return _orig_file_id(file_id)

    def _resolve_entry_with_registry(path):
        if isinstance(path, str):
            key = normalize_path(path)
            if key in _by_path:
                return _by_path[key]
        return _orig_resolve_entry(path)

    client._resolve_dir_id = _resolve_dir_id_with_registry
    client.file.id = _file_id_with_registry
    client.file._resolve_entry = _resolve_entry_with_registry


class SharedStructure:
    """Lazily-initialised shared remote file structure for client integration tests.

    Each property is created on first access and cached. The entry is
    immediately registered in the client registry so subsequent lookups do
    not make API calls.

    Remote hierarchy (relative to root_dir)::

        root_dir/
        ├── dir_a/          # empty work directory
        ├── dir_b/          # empty work directory
        ├── f_<hex>.bin     # file_small  (64 B)
        └── f_<hex>.bin     # file_large  (4 KB)
    """

    def __init__(self, api_client: Client, root_dir: Directory) -> None:
        self._api_client = api_client
        self.root_dir = root_dir

    @cached_property
    def dir_a(self) -> Directory:
        entry = self._api_client.file.create_directory(f"{self.root_dir.path}/dir_a")
        self._api_client.register_entry(entry)
        return entry

    @cached_property
    def dir_b(self) -> Directory:
        entry = self._api_client.file.create_directory(f"{self.root_dir.path}/dir_b")
        self._api_client.register_entry(entry)
        return entry

    @cached_property
    def file_small(self) -> File:
        entry = upload_file(self._api_client, self.root_dir.path, size=64)
        self._api_client.register_entry(entry)
        return entry

    @cached_property
    def file_large(self) -> File:
        entry = upload_file(self._api_client, self.root_dir.path, size=4096)
        self._api_client.register_entry(entry)
        return entry


@pytest.fixture(scope="session")
def api_client():
    cookie_str = os.environ.get("TEST_COOKIE_115CLI", "")
    if not cookie_str:
        pytest.skip("TEST_COOKIE_115CLI not set")

    cookies = parse_cookie_string(cookie_str)
    uid = cookies.get("UID", "")
    cid = cookies.get("CID", "")
    seid = cookies.get("SEID", "")
    kid = cookies.get("KID", "")
    if not all([uid, cid, seid, kid]):
        pytest.skip("TEST_COOKIE_115CLI must contain UID, CID, SEID, KID")

    # set up proxy for tests
    proxy_url = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
    if proxy_url:
        proxy_pool = httpcore.HTTPProxy(proxy_url, http2=True)
        httpcore_request._DEFAULT_CLIENT = proxy_pool

    auth = CookieAuth(uid=uid, cid=cid, seid=seid, kid=kid)
    client = create_client(auth)
    _patch_client_registry(client)

    p115client.logger.addHandler(_log_capture)
    p115client.logger.setLevel(logging.DEBUG)

    _orig_request = httpcore_request.request

    def _rate_limited_request(*args, **kwargs):
        time.sleep(0.05)  # avoid hitting server rate limits during tests
        return _orig_request(*args, **kwargs)

    patcher = unittest.mock.patch("httpcore_request.request", _rate_limited_request)
    patcher.start()

    yield client

    patcher.stop()
    p115client.logger.removeHandler(_log_capture)


@pytest.fixture(scope="session")
def root_dir(api_client):
    try:
        root = api_client.file.create_directory(TEST_ROOT)
    except FileExistsError:
        root = api_client.file.stat(TEST_ROOT)

    api_client.register_entry(root)

    yield root

    api_client.unregister_entry(root)
    time.sleep(0.5)
    api_client.file.delete(root, recursive=True)


@pytest.fixture(scope="session")
def shared(api_client, root_dir):
    return SharedStructure(api_client, root_dir)
