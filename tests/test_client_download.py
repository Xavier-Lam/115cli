import random
import time
import unittest

from cli115.client.base import CloudTask, Directory, DownloadQuota
from cli115.client.models import TaskStatus
from tests.base import BaseTestCase


def _random_image_url() -> str:
    w = random.randint(100, 800)
    h = random.randint(100, 600)
    bg = format(random.randint(0, 0xFFFFFF), "06x")
    fg = format(random.randint(0, 0xFFFFFF), "06x")
    return f"https://dummyimage.com/{w}x{h}/{bg}/{fg}.png"


class TestDownloadQuota(BaseTestCase):

    def test_quota_returns_info(self):
        quota = self.client.download.quota()
        self.assertIsInstance(quota, DownloadQuota)
        self.assertGreater(quota.total, 0)
        self.assertGreaterEqual(quota.quota, 0)


class TestDownloadAddAndDelete(BaseTestCase):

    def setUp(self):
        self._hashes_to_delete: list[str] = []

    def tearDown(self):
        if self._hashes_to_delete:
            time.sleep(0.5)
            self.client.download.delete(*self._hashes_to_delete)

    def test_add_url(self):
        current_total = len(self.client.download.list())
        task = self.client.download.add_url(_random_image_url())
        self._hashes_to_delete.append(task.info_hash)
        self.assertIsInstance(task, CloudTask)
        self.assertTrue(task.info_hash)
        self.assertIn(task.status, list(TaskStatus))
        collection = self.client.download.list()
        self.assertEqual(len(collection), current_total + 1)
        self.assertTrue(any(t.info_hash == task.info_hash for t in collection))

    def test_add_url_with_dest_dir(self):
        task = self.client.download.add_url(
            _random_image_url(), dest_dir=self.test_root_dir
        )
        self._hashes_to_delete.append(task.info_hash)
        self.assertIsInstance(task, CloudTask)
        self.assertTrue(task.info_hash)
        # Validate folder_id matches the destination directory
        if task.folder_id:
            folder_entry = self.client.file.id(task.folder_id)
            self.assertIsInstance(folder_entry, Directory)
            self.assertEqual(task.folder_id, self.test_root_dir.id)

    def test_add_urls(self):
        current_total = len(self.client.download.list())
        urls = [_random_image_url(), _random_image_url()]
        tasks = self.client.download.add_urls(*urls)
        for t in tasks:
            self._hashes_to_delete.append(t.info_hash)
        self.assertEqual(len(tasks), 2)
        for task in tasks:
            self.assertIsInstance(task, CloudTask)
            self.assertTrue(task.info_hash)
        collection = self.client.download.list()
        self.assertEqual(len(collection), current_total + 2)
        for task in tasks:
            self.assertTrue(any(t.info_hash == task.info_hash for t in collection))


if __name__ == "__main__":
    unittest.main()
