import hashlib
import unittest

from cli115.client import File
from tests.base import BaseTestCase


class TestFetch(BaseTestCase):

    _entry: File

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        entry, _ = cls.upload_file(size=4096)
        cls._entry = entry

    def test_fetch_read_full_content(self):
        with self.client.file.fetch(self._entry) as rf:
            data = rf.read()
        sha1 = hashlib.sha1(data).hexdigest().upper()
        self.assertEqual(sha1, self._entry.sha1)
        self.assertEqual(len(data), self._entry.size)

        # partial read
        with self.client.file.fetch(self._entry) as rf:
            # Read first 100 bytes
            chunk1 = rf.read(100)
            self.assertEqual(len(chunk1), 100)
            self.assertEqual(rf.tell(), 100)

            # Read next 200 bytes
            chunk2 = rf.read(200)
            self.assertEqual(len(chunk2), 200)
            self.assertEqual(rf.tell(), 300)

        self.assertEqual(data[:100], chunk1)
        self.assertEqual(data[100:300], chunk2)

    def test_fetch_seekable_readable(self):
        with self.client.file.fetch(self._entry.path) as rf:
            self.assertEqual(rf.name, self._entry.name)
            self.assertTrue(rf.seekable())
            self.assertTrue(rf.readable())
            self.assertFalse(rf.writable())


if __name__ == "__main__":
    unittest.main()
