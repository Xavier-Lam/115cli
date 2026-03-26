"""Base test class for cli115 integration tests.

Reads 115CLI_TEST_COOKIE from environment and manages
a test folder '/115cli_test' that is created before the
entire test suite and removed after.
"""

import hashlib
import os
import tempfile
import time
import unittest
import unittest.mock
import uuid

from cli115.auth import CookieAuth
from cli115.client import Client, Directory, File, create_client
from cli115.exceptions import AlreadyExistsError

TEST_ROOT = "/115cli_test"


def _parse_cookie_string(cookie_str: str) -> dict[str, str]:
    cookies = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            key, value = part.split("=", 1)
            cookies[key.strip()] = value.strip()
    return cookies


def create_temp_file(content: bytes, name: str = "") -> str:
    """Create a temporary file with the given content and return its path.

    If *name* is given the file is created with that basename inside a
    temporary directory so that 115 sees the desired filename.
    """
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


class BaseTestCase(unittest.TestCase):
    """Base class for integration tests.

    Creates /115cli_test before the suite and removes it after.
    """

    client: Client
    test_root_dir: Directory

    @classmethod
    def setUpClass(cls):
        cookie_str = os.environ.get("TEST_COOKIE_115CLI", "")
        if not cookie_str:
            raise unittest.SkipTest("TEST_COOKIE_115CLI not set")

        cookies = _parse_cookie_string(cookie_str)
        uid = cookies.get("UID", "")
        cid = cookies.get("CID", "")
        seid = cookies.get("SEID", "")
        kid = cookies.get("KID", "")
        if not all([uid, cid, seid, kid]):
            raise unittest.SkipTest(
                "TEST_COOKIE_115CLI must contain UID, CID, SEID, KID"
            )

        # Replace httpcore_request's default session with an HTTPProxy if
        # HTTP_PROXY / HTTPS_PROXY is set.  httpcore.ConnectionPool does
        # NOT read proxy environment variables automatically.
        import httpcore
        import httpcore_request as _httpcore_request

        proxy_url = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
        if proxy_url:
            proxy_pool = httpcore.HTTPProxy(
                proxy_url, http2=True, max_connections=128, retries=5
            )
            _httpcore_request._DEFAULT_CLIENT = proxy_pool

        auth = CookieAuth(uid=uid, cid=cid, seid=seid, kid=kid)
        cls.client = create_client(auth)

        # Patch httpcore_request.request to sleep 0.05 s before every HTTP
        # request.  This global rate-limit prevents triggering the Aliyun WAF
        # that blocks repeated requests sent in rapid succession (HTTP 405).
        _orig_request = _httpcore_request.request

        def _rate_limited_request(*args, **kwargs):
            time.sleep(0.05)
            return _orig_request(*args, **kwargs)

        patcher = unittest.mock.patch("httpcore_request.request", _rate_limited_request)
        patcher.start()
        cls.addClassCleanup(patcher.stop)

        # Hijack _resolve_dir_id on the WebAPIClient so that TEST_ROOT is
        # resolved directly from the cached id (no extra network call).
        _orig = cls.client._resolve_dir_id

        def _resolve_dir_id_cached(path):
            if isinstance(path, str) and path == TEST_ROOT:
                return cls.test_root_dir.id
            return _orig(path)

        cls.client._resolve_dir_id = _resolve_dir_id_cached

        try:
            cls.test_root_dir = cls.client.file.create_directory(TEST_ROOT)
        except AlreadyExistsError:
            cls.test_root_dir = cls.client.file.stat(TEST_ROOT)

    @classmethod
    def tearDownClass(cls):
        # the previous operations may not complete yet, delete the folder may
        # fail with "990009" error
        time.sleep(0.5)
        cls.client.file.delete(cls.test_root_dir, recursive=True)

    @classmethod
    def upload_file(
        cls, dest_dir: str | None = None, *, fname: str = "", size: int = 64
    ) -> tuple[File, str]:
        """Upload a file of *size* random bytes to *dest_dir* (default:
        TEST_ROOT).

        Returns ``(file_entry, sha1)`` where *file_entry* is the
        :class:`File` object returned by the upload (containing ``id``,
        ``path`` and ``name``) and *sha1* is the expected SHA-1 hex digest
        (upper-case).
        """
        if dest_dir is None:
            dest_dir = TEST_ROOT
        if not fname:
            fname = f"f_{uuid.uuid4().hex[:8]}.bin"
        content = os.urandom(size)
        sha1 = hashlib.sha1(content).hexdigest().upper()
        local = create_temp_file(content, name=fname)
        try:
            entry = cls.client.file.upload(f"{dest_dir}/{fname}", local)
        finally:
            os.unlink(local)
            os.rmdir(os.path.dirname(local))
        return entry, sha1
