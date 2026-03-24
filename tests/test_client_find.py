import time
import unittest
import uuid

from tests.base import TEST_ROOT, BaseTestCase


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class TestFind(BaseTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # /115cli_test/
        #     find_<uid>/
        #         root.bin          ← file at top level of the search scope
        #         folder_<uid>/
        #             sub.bin       ← file inside a subdirectory

        # Root folder for all find tests
        cls.root_name = _unique("find")
        cls.root_path = f"{TEST_ROOT}/{cls.root_name}"
        cls.root_dir = cls.client.file.create_directory(cls.root_path)
        cls.root_file, _ = cls.upload_file(cls.root_path, fname="root.bin")

        # Sub-directory
        cls.sub_name = _unique("folder")
        cls.sub_path = f"{cls.root_path}/{cls.sub_name}"
        cls.sub_dir = cls.client.file.create_directory(cls.sub_path)
        cls.sub_file, _ = cls.upload_file(cls.sub_path, fname="sub.bin")

        # Give the server a moment to index the changes
        time.sleep(1)

    def test_find(self):
        entries, pagination = self.client.file.find("sub.bin", path=self.sub_dir.path)
        self.assertEqual(entries[0].id, self.sub_file.id)
        self.assertEqual(entries[0].name, self.sub_file.name)
        self.assertFalse(entries[0].is_directory)
        self.assertEqual(entries[0].parent_id, self.sub_dir.id)
        self.assertEqual(pagination.total, 1)

        # search in subdirectory
        entries, pagination = self.client.file.find("sub", path=self.root_dir)
        self.assertEqual(entries[0].id, self.sub_file.id)
        self.assertEqual(entries[0].name, self.sub_file.name)
        self.assertFalse(entries[0].is_directory)
        self.assertEqual(entries[0].parent_id, self.sub_dir.id)
        self.assertEqual(pagination.total, 1)

        # search for a folder
        entries, pagination = self.client.file.find(self.sub_name, path=self.root_dir)
        self.assertEqual(entries[0].id, self.sub_dir.id)
        self.assertEqual(entries[0].name, self.sub_dir.name)
        self.assertTrue(entries[0].is_directory)
        self.assertEqual(entries[0].parent_id, self.root_dir.id)
        self.assertEqual(pagination.total, 1)

        # search for a non-existent file
        entries, pagination = self.client.file.find("root.bin", path=self.sub_dir)
        self.assertEqual(len(entries), 0)
        self.assertEqual(pagination.total, 0)

    def test_find_global_search(self):
        entries, pagination = self.client.file.find(self.sub_dir.name)
        self.assertEqual(entries[0].id, self.sub_dir.id)
        self.assertEqual(entries[0].name, self.sub_dir.name)
        self.assertEqual(entries[0].parent_id, self.root_dir.id)
        self.assertTrue(entries[0].is_directory)
        self.assertEqual(pagination.total, 1)


if __name__ == "__main__":
    unittest.main()
