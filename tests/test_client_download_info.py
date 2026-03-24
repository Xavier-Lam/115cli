import hashlib
import unittest
import urllib.request

from cli115.client.base import DownloadInfo
from tests.base import BaseTestCase


class TestDownloadInfo(BaseTestCase):

    _remote_path: str
    _uploaded_sha1: str

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        entry, sha1 = cls.upload_file(size=4096)
        cls._remote_path = entry.path
        cls._uploaded_sha1 = sha1

    def test_download_info_returns_valid_object(self):
        info = self.client.file.download_info(self._remote_path)
        self.assertIsInstance(info, DownloadInfo)
        self.assertTrue(info.url.startswith("http"))
        self.assertTrue(info.file_name)
        self.assertGreater(info.file_size, 0)
        self.assertTrue(info.sha1)
        self.assertEqual(info.referer, "https://115.com/")

    def test_download_info_has_user_agent(self):
        info = self.client.file.download_info(self._remote_path)
        self.assertTrue(info.user_agent)

    def test_download_info_has_cookies(self):
        info = self.client.file.download_info(self._remote_path)
        self.assertIn("UID", info.cookies)
        self.assertIn("CID", info.cookies)

    def test_download_content_matches_upload(self):
        info = self.client.file.download_info(self._remote_path)
        req = urllib.request.Request(
            info.url,
            headers={
                "User-Agent": info.user_agent,
                "Cookie": info.cookies,
                "Referer": info.referer,
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            downloaded = resp.read()
        downloaded_sha1 = hashlib.sha1(downloaded).hexdigest().upper()
        self.assertEqual(downloaded_sha1, self._uploaded_sha1)


if __name__ == "__main__":
    unittest.main()
