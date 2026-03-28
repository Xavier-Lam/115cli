import random
import time

from cli115.client.base import CloudTask, Directory, DownloadQuota
from cli115.client.models import TaskStatus


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

    def test_add_url(self, api_client, root_dir):
        hashes = []
        try:
            current_total = len(api_client.download.list())
            task = api_client.download.add_url(_random_image_url())
            hashes.append(task.info_hash)
            assert isinstance(task, CloudTask)
            assert task.info_hash
            assert task.status in list(TaskStatus)
            collection = api_client.download.list()
            assert len(collection) == current_total + 1
            assert any(t.info_hash == task.info_hash for t in collection)

            # with dest directory
            task = api_client.download.add_url(
                _random_image_url(), dest_dir=root_dir.path
            )
            hashes.append(task.info_hash)
            assert isinstance(task, CloudTask)
            assert task.info_hash
            if task.folder_id:
                folder_entry = api_client.file.id(task.folder_id)
                assert isinstance(folder_entry, Directory)
                assert task.folder_id == root_dir.id
        finally:
            if hashes:
                time.sleep(0.5)
                api_client.download.delete(*hashes)

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
