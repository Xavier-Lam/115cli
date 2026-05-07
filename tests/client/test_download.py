import random
import time
from unittest.mock import MagicMock

import pytest

from cli115.client.base import CloudTask, DownloadQuota
from tests.client.conftest import make_client


def _random_image_url():
    w = random.randint(100, 800)
    h = random.randint(100, 600)
    bg = format(random.randint(0, 0xFFFFFF), "06x")
    fg = format(random.randint(0, 0xFFFFFF), "06x")
    return f"https://dummyimage.com/{w}x{h}/{bg}/{fg}.png"


class TestDownloadQuota:

    def test_quota_returns_info(self, api_client):
        quota = api_client.download.quota()
        assert isinstance(quota, DownloadQuota)
        assert quota.total > 0
        assert quota.quota >= 0


class TestDownloadAddAndDelete:

    def test_add_urls(self, api_client):
        hashes = []
        try:
            current_total = len(api_client.download.list())
            urls = [_random_image_url(), _random_image_url()]
            tasks = api_client.download.add_urls(*urls)
            for t in tasks:
                hashes.append(t.info_hash)
            assert len(tasks) == 2
            for task in tasks:
                assert isinstance(task, CloudTask)
                assert task.info_hash
            collection = api_client.download.list()
            assert len(collection) == current_total + 2
            for task in tasks:
                assert any(t.info_hash == task.info_hash for t in collection)
        finally:
            if hashes:
                time.sleep(0.5)
                api_client.download.delete(*hashes)

    def test_add_urls_with_nonexistent_dest(self):
        client = make_client()
        # id=0 signals the destination directory does not exist

        def mock_get(url, **kwargs):
            resp = MagicMock()
            if url.endswith("/files/getid"):
                resp.json.return_value = {"id": 0}
            return resp

        client.download._client.get.side_effect = mock_get
        with pytest.raises(FileNotFoundError):
            client.download.add_urls(
                "http://example.com/file.zip", dest_dir="/nonexistent"
            )
