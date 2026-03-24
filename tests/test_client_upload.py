import hashlib
import io
import unittest
import uuid

from cli115.client import File
from tests.base import TEST_ROOT, BaseTestCase


class TestUpload(BaseTestCase):

    def test_upload_file_with_hash(self):
        entry, expected_sha1 = self.upload_file(size=1024)
        self.assertIsInstance(entry, File)
        self.assertEqual(len(entry.sha1), 40)
        self.assertEqual(entry.sha1, expected_sha1)
        self.assertEqual(entry.size, 1024)

    def test_upload_file_like_object(self):
        content = uuid.uuid4().bytes * 64
        expected_sha1 = hashlib.sha1(content).hexdigest().upper()
        buf = io.BytesIO(content)
        buf.name = f"up_buf_{uuid.uuid4().hex[:8]}.bin"
        result = self.client.file.upload(f"{TEST_ROOT}/{buf.name}", buf)
        self.assertIsInstance(result, File)
        self.assertEqual(result.sha1, expected_sha1)


if __name__ == "__main__":
    unittest.main()
