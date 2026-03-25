import time
import unittest
import uuid

from cli115.client import Directory, File, SortField, SortOrder
from cli115.exceptions import (
    AlreadyExistsError,
    DirectoryNotEmptyError,
    NotFoundError,
)
from tests.base import TEST_ROOT, BaseTestCase


# -- helpers --


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# -- tests --


class TestId(BaseTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.dir_name = _unique("id_dir")
        cls.dir_entry = cls.client.file.create_directory(f"{TEST_ROOT}/{cls.dir_name}")
        cls.file_entry, _ = cls.upload_file()

    def test_id_returns_directory(self):
        result = self.client.file.id(self.dir_entry.id)
        self.assertIsInstance(result, Directory)
        self.assertEqual(result.id, self.dir_entry.id)
        self.assertEqual(result.name, self.dir_name)
        self.assertEqual(result.path, f"{TEST_ROOT}/{self.dir_name}")

    def test_id_returns_file(self):
        result = self.client.file.id(self.file_entry.id)
        self.assertIsInstance(result, File)
        self.assertEqual(result.id, self.file_entry.id)
        self.assertEqual(result.name, self.file_entry.name)
        self.assertEqual(result.path, f"{TEST_ROOT}/{self.file_entry.name}")

    def test_id_nonexistent_raises_not_found(self):
        with self.assertRaises(NotFoundError):
            self.client.file.id("999999999999999")


class TestInfo(BaseTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.info_name = _unique("info")
        cls.client.file.create_directory(f"{TEST_ROOT}/{cls.info_name}")
        info_entry, _ = cls.upload_file()
        cls.info_fname = info_entry.name

    def test_info_returns_directory(self):
        path = f"{TEST_ROOT}/{self.info_name}"
        result = self.client.file.info(path)
        self.assertIsInstance(result, Directory)
        self.assertTrue(result.is_directory)
        self.assertEqual(result.name, self.info_name)
        self.assertEqual(result.path, path)
        self.assertTrue(result.id)
        self.assertTrue(result.parent_id)

    def test_info_returns_file(self):
        path = f"{TEST_ROOT}/{self.info_fname}"
        result = self.client.file.info(path)
        self.assertIsInstance(result, File)
        self.assertFalse(result.is_directory)
        self.assertEqual(result.name, self.info_fname)
        self.assertEqual(result.path, path)
        self.assertTrue(result.id)
        self.assertGreater(result.size, 0)
        self.assertTrue(result.sha1)


class TestList(BaseTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.name_a = _unique("list_a")
        cls.name_b = _unique("list_b")
        cls.client.file.create_directory(f"{TEST_ROOT}/{cls.name_a}")
        cls.client.file.create_directory(f"{TEST_ROOT}/{cls.name_b}")

        # A dedicated folder for mixed-content and sort-order tests.
        cls.sort_dir = _unique("list_sort")
        cls.client.file.create_directory(f"{TEST_ROOT}/{cls.sort_dir}")
        cls.client.file.create_directory(f"{TEST_ROOT}/{cls.sort_dir}/zzz")
        cls.client.file.create_directory(f"{TEST_ROOT}/{cls.sort_dir}/aaa")

        cls.mixed_dir = _unique("list_mixed")
        cls.mixed_subdir = "mixed_subdir"
        cls.client.file.create_directory(f"{TEST_ROOT}/{cls.mixed_dir}")
        cls.client.file.create_directory(
            f"{TEST_ROOT}/{cls.mixed_dir}/{cls.mixed_subdir}"
        )
        mixed_entry, _ = cls.upload_file(f"{TEST_ROOT}/{cls.mixed_dir}")
        cls.mixed_fname = mixed_entry.name

    def test_list_returns_created_folders(self):
        items, pagination = self.client.file.list(TEST_ROOT)
        names = {item.name for item in items}
        self.assertIn(self.name_a, names)
        self.assertIn(self.name_b, names)
        paths = {item.path for item in items}
        self.assertIn(f"{TEST_ROOT}/{self.name_a}", paths)
        self.assertIn(f"{TEST_ROOT}/{self.name_b}", paths)

        # empty folder
        items, pagination = self.client.file.list(f"{TEST_ROOT}/{self.name_a}")
        self.assertEqual(len(items), 0)
        self.assertEqual(pagination.total, 0)

        # mixed folder
        items, _ = self.client.file.list(f"{TEST_ROOT}/{self.mixed_dir}")
        dirs = [i for i in items if isinstance(i, Directory)]
        files = [i for i in items if isinstance(i, File)]
        paths = {i.path for i in items}
        self.assertGreaterEqual(len(dirs), 1)
        self.assertGreaterEqual(len(files), 1)
        self.assertIn(self.mixed_subdir, {d.name for d in dirs})
        self.assertIn(self.mixed_fname, {f.name for f in files})
        self.assertIn(f"{TEST_ROOT}/{self.mixed_dir}/{self.mixed_subdir}", paths)
        self.assertIn(f"{TEST_ROOT}/{self.mixed_dir}/{self.mixed_fname}", paths)

        # nonexistent folder
        with self.assertRaises(NotFoundError):
            self.client.file.list(f"{TEST_ROOT}/nonexistent")

    def test_list_pagination(self):
        items, pagination = self.client.file.list(TEST_ROOT, limit=1, offset=0)
        self.assertEqual(len(items), 1)
        self.assertGreaterEqual(pagination.total, 2)
        fid1 = items[0].id
        items, pagination = self.client.file.list(TEST_ROOT, limit=1, offset=1)
        self.assertEqual(len(items), 1)
        self.assertGreaterEqual(pagination.total, 2)
        fid2 = items[0].id
        self.assertNotEqual(fid1, fid2)

    def test_list_sort_order(self):
        items, _ = self.client.file.list(
            f"{TEST_ROOT}/{self.sort_dir}",
            sort=SortField.FILENAME,
            sort_order=SortOrder.DESC,
        )
        names = [item.name for item in items]
        self.assertLess(names.index("zzz"), names.index("aaa"))

        items, _ = self.client.file.list(
            f"{TEST_ROOT}/{self.sort_dir}",
            sort=SortField.FILENAME,
            sort_order=SortOrder.ASC,
        )
        names = [item.name for item in items]
        self.assertLess(names.index("aaa"), names.index("zzz"))

        items, _ = self.client.file.list(
            f"{TEST_ROOT}/{self.sort_dir}",
            sort=SortField.CREATED_TIME,
            sort_order=SortOrder.DESC,
        )
        names = [item.name for item in items]
        self.assertLess(names.index("aaa"), names.index("zzz"))

        items, _ = self.client.file.list(
            f"{TEST_ROOT}/{self.sort_dir}",
            sort=SortField.CREATED_TIME,
            sort_order=SortOrder.ASC,
        )
        names = [item.name for item in items]
        self.assertLess(names.index("zzz"), names.index("aaa"))


class TestCreateDirectory(BaseTestCase):

    def test_create_directory(self):
        name = _unique("cdir")
        path = f"{TEST_ROOT}/{name}"
        folder = self.client.file.create_directory(path)
        self.assertTrue(folder.id)
        self.assertEqual(folder.name, name)
        self.assertEqual(folder.path, path)

        # verify it appears in the list
        items, _ = self.client.file.list(TEST_ROOT)
        names = {item.name for item in items}
        self.assertIn(name, names)

    def test_create_existing_directory_raises(self):
        name = _unique("cdir_exists")
        path = f"{TEST_ROOT}/{name}"
        self.client.file.create_directory(path)
        with self.assertRaises(AlreadyExistsError):
            self.client.file.create_directory(path)

    def test_create_directory_with_nonexistent_parent(self):
        parent_name = _unique("cdir_np")
        child_name = "child"
        path = f"{TEST_ROOT}/{parent_name}/{child_name}"
        folder = self.client.file.create_directory(path, parents=True)
        self.assertEqual(folder.name, child_name)
        self.assertEqual(folder.path, path)
        # parent was created implicitly
        items, _ = self.client.file.list(f"{TEST_ROOT}/{parent_name}")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].name, child_name)


class TestDelete(BaseTestCase):

    def test_delete_directory(self):
        name = _unique("deld")
        self.client.file.create_directory(f"{TEST_ROOT}/{name}")
        self.client.file.delete(f"{TEST_ROOT}/{name}")
        items, _ = self.client.file.list(TEST_ROOT)
        names = {item.name for item in items}
        self.assertNotIn(name, names)

    def test_delete_file(self):
        entry, _ = self.upload_file()
        self.client.file.delete(entry.path)
        items, _ = self.client.file.list(TEST_ROOT)
        names = {item.name for item in items}
        self.assertNotIn(entry.name, names)

    def test_batch_delete(self):
        name1 = _unique("bdel1")
        name2 = _unique("bdel2")
        self.client.file.create_directory(f"{TEST_ROOT}/{name1}")
        self.client.file.create_directory(f"{TEST_ROOT}/{name2}")
        self.client.file.batch_delete(
            f"{TEST_ROOT}/{name1}",
            f"{TEST_ROOT}/{name2}",
        )
        items, _ = self.client.file.list(TEST_ROOT)
        names = {item.name for item in items}
        self.assertNotIn(name1, names)
        self.assertNotIn(name2, names)

    def test_delete_recursive(self):
        name = _unique("del_nonempty")
        dir_path = f"{TEST_ROOT}/{name}"
        self.client.file.create_directory(dir_path)
        self.client.file.create_directory(f"{dir_path}/inner")
        with self.assertRaises(DirectoryNotEmptyError):
            self.client.file.delete(dir_path, recursive=False)

        name = _unique("del_rec")
        dir_path = f"{TEST_ROOT}/{name}"
        self.client.file.create_directory(dir_path)
        self.client.file.create_directory(f"{dir_path}/inner")
        self.client.file.delete(dir_path, recursive=True)
        items, _ = self.client.file.list(TEST_ROOT)
        self.assertNotIn(name, {i.name for i in items})


class TestMove(BaseTestCase):

    def setUp(self):
        self.src_name = _unique("move_src")
        self.dest_name = _unique("move_dest")
        self.src_path = f"{TEST_ROOT}/{self.src_name}"
        self.dest_path = f"{TEST_ROOT}/{self.dest_name}"
        self.client.file.create_directory(self.src_path)
        self.client.file.create_directory(self.dest_path)

    def tearDown(self):
        for path in [self.src_path, self.dest_path]:
            try:
                self.client.file.delete(path)
            except Exception:
                pass

    def test_move_directory(self):
        child = "move_child_dir"
        self.client.file.create_directory(f"{self.src_path}/{child}")
        self.client.file.move(f"{self.src_path}/{child}", self.dest_path)
        dest_names = {i.name for i in self.client.file.list(self.dest_path)[0]}
        src_names = {i.name for i in self.client.file.list(self.src_path)[0]}
        self.assertIn(child, dest_names)
        self.assertNotIn(child, src_names)

    def test_move_file(self):
        entry, _ = self.upload_file(self.src_path)
        self.client.file.move(entry.path, self.dest_path)
        dest_names = {i.name for i in self.client.file.list(self.dest_path)[0]}
        src_names = {i.name for i in self.client.file.list(self.src_path)[0]}
        self.assertIn(entry.name, dest_names)
        self.assertNotIn(entry.name, src_names)

    def test_batch_move(self):
        self.client.file.create_directory(f"{self.src_path}/batch_move_1")
        self.client.file.create_directory(f"{self.src_path}/batch_move_2")
        self.client.file.batch_move(
            f"{self.src_path}/batch_move_1",
            f"{self.src_path}/batch_move_2",
            dest_dir=self.dest_path,
        )
        dest_names = {i.name for i in self.client.file.list(self.dest_path)[0]}
        src_items, _ = self.client.file.list(self.src_path)
        self.assertIn("batch_move_1", dest_names)
        self.assertIn("batch_move_2", dest_names)
        self.assertEqual(len(src_items), 0)


class TestCopy(BaseTestCase):

    def setUp(self):
        self.src_name = _unique("copy_src")
        self.dest_name = _unique("copy_dest")
        self.src_path = f"{TEST_ROOT}/{self.src_name}"
        self.dest_path = f"{TEST_ROOT}/{self.dest_name}"
        self.client.file.create_directory(self.src_path)
        self.client.file.create_directory(self.dest_path)

    def tearDown(self):
        for path in [self.src_path, self.dest_path]:
            try:
                self.client.file.delete(path)
            except Exception:
                pass

    def test_copy_directory(self):
        child = "copy_child_dir"
        self.client.file.create_directory(f"{self.src_path}/{child}")
        self.client.file.copy(f"{self.src_path}/{child}", self.dest_path)
        dest_names = {i.name for i in self.client.file.list(self.dest_path)[0]}
        src_names = {i.name for i in self.client.file.list(self.src_path)[0]}
        self.assertIn(child, dest_names)
        self.assertIn(child, src_names)

    def test_copy_file(self):
        entry, _ = self.upload_file(self.src_path)
        self.client.file.copy(entry.path, self.dest_path)
        dest_names = {i.name for i in self.client.file.list(self.dest_path)[0]}
        src_names = {i.name for i in self.client.file.list(self.src_path)[0]}
        self.assertIn(entry.name, dest_names)
        self.assertIn(entry.name, src_names)

    def test_batch_copy(self):
        self.client.file.create_directory(f"{self.src_path}/batch_copy_1")
        self.client.file.create_directory(f"{self.src_path}/batch_copy_2")
        self.client.file.batch_copy(
            f"{self.src_path}/batch_copy_1",
            f"{self.src_path}/batch_copy_2",
            dest_dir=self.dest_path,
        )
        dest_names = {i.name for i in self.client.file.list(self.dest_path)[0]}
        self.assertIn("batch_copy_1", dest_names)
        self.assertIn("batch_copy_2", dest_names)
        src_items, _ = self.client.file.list(self.src_path)
        self.assertEqual(len(src_items), 2)


class TestRename(BaseTestCase):

    def test_rename_directory(self):
        old_name = _unique("rend")
        new_name = _unique("rend_new")
        old_path = f"{TEST_ROOT}/{old_name}"
        self.client.file.create_directory(old_path)
        self.client.file.rename(old_path, new_name)
        result = self.client.file.info(f"{TEST_ROOT}/{new_name}")
        self.assertEqual(result.name, new_name)
        # cleanup
        try:
            self.client.file.delete(f"{TEST_ROOT}/{new_name}")
        except Exception:
            pass

    def test_rename_file(self):
        entry, _ = self.upload_file()
        new_name = f"renf_new_{uuid.uuid4().hex[:8]}.bin"
        self.client.file.rename(entry.path, new_name)
        result = self.client.file.info(f"{TEST_ROOT}/{new_name}")
        self.assertEqual(result.name, new_name)
        try:
            self.client.file.delete(f"{TEST_ROOT}/{new_name}")
        except Exception:
            pass


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
        self.assertTrue(info.url.startswith("http"))
        self.assertTrue(info.file_name)
        self.assertGreater(info.file_size, 0)
        self.assertTrue(info.sha1)
        self.assertEqual(info.referer, "https://115.com/")
        self.assertTrue(info.user_agent)
        self.assertIn("UID", info.cookies)
        self.assertIn("CID", info.cookies)


if __name__ == "__main__":
    unittest.main()
