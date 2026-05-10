from functools import cached_property
import hashlib
import logging
import os
import tempfile
import time
import uuid
from unittest.mock import MagicMock, patch

from httpx import HTTPTransport, Request, RequestNotRead, Response
import pytest

from cli115.auth import CookieAuth
from cli115.client import Client, create_client, Directory, File, general
from cli115.helpers import normalize_path, parse_cookie_string

TEST_ROOT = "/115cli_test"


def make_client():
    """Create a General client with a fully mocked P115 API backend."""
    with patch("cli115.client.general.base.APIClient"):
        client = general.Client(MagicMock())
    mock_client = MagicMock()
    client._account._api = mock_client
    client._file._api = mock_client
    client._download._api = mock_client
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
    terminalreporter.write_sep(
        "=",
        f"API requests: {len(records)} total",
    )
    for msg in records:
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

    _orig_file_resolve_dir_id = client.file._resolve_dir_id
    _orig_download_resolve_dir_id = client.download._resolve_dir_id
    _orig_file_id = client.file.id
    _orig_resolve_entry = client.file._resolve_entry

    def _make_resolve_dir_id_with_registry(orig):
        def _resolve_dir_id_with_registry(path):
            if isinstance(path, Directory):
                return path.id
            if isinstance(path, str):
                key = normalize_path(path)
                if key in _by_path:
                    return _by_path[key].id
            return orig(path)

        return _resolve_dir_id_with_registry

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

    client.file._resolve_dir_id = _make_resolve_dir_id_with_registry(
        _orig_file_resolve_dir_id
    )
    client.download._resolve_dir_id = _make_resolve_dir_id_with_registry(
        _orig_download_resolve_dir_id
    )
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

    class DebugTransport(HTTPTransport):
        @cached_property
        def logger(self):
            return logging.getLogger("cli115.test_api_client")

        def handle_request(self, request: Request) -> Response:
            # log the request details before sending
            message = (
                f"Requesting {request.method} "
                f"{request.url.scheme}://{request.url.host}{request.url.path}"
            )
            params = request.url.params
            if params:
                message += f"\n    └─ Params: {params}"
            try:
                data = request.content
            except RequestNotRead:
                data = b"<streaming request body>"
            if data:
                message += f"\n    └─ Payload: {data}"
            self.logger.debug(message)

            time.sleep(0.05)  # avoid hitting server rate limits during tests

            return super().handle_request(request)

    transport = DebugTransport()
    transport.logger.addHandler(_log_capture)
    transport.logger.setLevel(logging.DEBUG)

    auth = CookieAuth(uid=uid, cid=cid, seid=seid, kid=kid)
    client = create_client(auth, transport=transport)
    _patch_client_registry(client)
    try:
        yield client
    finally:
        transport.logger.removeHandler(_log_capture)


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
