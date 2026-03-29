import hashlib
import time
from unittest.mock import MagicMock

import pytest

from cli115.client import Directory, File, SortField, SortOrder
from tests.client.conftest import make_client, make_dir, make_file, upload_file


class TestId:

    def test_id(self, api_client, shared):
        # directory
        result = api_client.file.id(shared.dir_a.id)
        assert isinstance(result, Directory)
        assert result.id == shared.dir_a.id
        assert result.name == shared.dir_a.name
        assert result.path == shared.dir_a.path

        # file
        result = api_client.file.id(shared.file_small.id)
        assert isinstance(result, File)
        assert result.id == shared.file_small.id
        assert result.name == shared.file_small.name
        assert result.path == shared.file_small.path

    def test_id_nonexistent(self):
        client = make_client()
        client._api.fs_file.return_value = {"state": True, "data": []}
        with pytest.raises(FileNotFoundError):
            client.file.id("999999999999999")


class TestStat:

    def test_stat_directory(self, api_client, shared):
        result = api_client.file.stat(shared.dir_a.path)
        assert isinstance(result, Directory)
        assert result.is_directory
        assert result.name == shared.dir_a.name
        assert result.path == shared.dir_a.path
        assert result.id == shared.dir_a.id
        assert result.parent_id == shared.dir_a.parent_id

    def test_stat_file(self, api_client, shared):
        result = api_client.file.stat(shared.file_small.path)
        assert isinstance(result, File)
        assert not result.is_directory
        assert result.name == shared.file_small.name
        assert result.path == shared.file_small.path
        assert result.id == shared.file_small.id
        assert result.parent_id == shared.file_small.parent_id
        assert result.size == shared.file_small.size
        assert result.sha1 == shared.file_small.sha1

    def test_stat_nonexistent(self):
        client = make_client()
        client._api.fs_dir_getid.return_value = {"state": True, "id": "100"}
        client._api.fs_files.return_value = {"state": True, "count": 0, "data": []}
        with pytest.raises(FileNotFoundError):
            client.file.stat("/parent/nonexistent")


class TestList:

    @pytest.fixture(scope="class")
    def sort_dir(self, api_client, shared):
        d = api_client.file.create_directory(f"{shared.root_dir.path}/sort")
        api_client.file.create_directory(f"{d.path}/zzz")
        api_client.file.create_directory(f"{d.path}/aaa")
        api_client.register_entry(d)
        yield d
        api_client.unregister_entry(d)

    def test_list(self, api_client, shared):
        # trigger creation before listing so all items are present
        dir_a = shared.dir_a
        dir_b = shared.dir_b
        file_small = shared.file_small
        file_large = shared.file_large

        items = api_client.file.list(shared.root_dir)
        by_name = {item.name: item for item in items}

        # dir_a is present with correct attributes
        assert dir_a.name in by_name
        dir_a_item = by_name[dir_a.name]
        assert isinstance(dir_a_item, Directory)
        assert dir_a_item.is_directory
        assert dir_a_item.path == dir_a.path
        assert dir_a_item.id == dir_a.id

        # dir_b is present
        assert dir_b.name in by_name

        # file_small is present with correct attributes
        assert file_small.name in by_name
        file_item = by_name[file_small.name]
        assert isinstance(file_item, File)
        assert not file_item.is_directory
        assert file_item.size == file_small.size
        assert file_item.sha1 == file_small.sha1
        assert file_item.id == file_small.id

        # file_large is present
        assert file_large.name in by_name

        # empty directory
        collection = api_client.file.list(shared.dir_a)
        assert len(collection) == 0

    def test_list_nonexistent_raises(self, api_client, shared):
        with pytest.raises(FileNotFoundError):
            api_client.file.list(f"{shared.root_dir.path}/nonexistent")

    def test_list_sort_order(self, api_client, sort_dir):
        items = api_client.file.list(
            sort_dir, sort=SortField.FILENAME, sort_order=SortOrder.DESC
        )
        names = [item.name for item in items]
        assert names.index("zzz") < names.index("aaa")

        items = api_client.file.list(
            sort_dir, sort=SortField.FILENAME, sort_order=SortOrder.ASC
        )
        names = [item.name for item in items]
        assert names.index("aaa") < names.index("zzz")

        items = api_client.file.list(
            sort_dir, sort=SortField.CREATED_TIME, sort_order=SortOrder.DESC
        )
        names = [item.name for item in items]
        assert names.index("aaa") < names.index("zzz")

        items = api_client.file.list(
            sort_dir, sort=SortField.CREATED_TIME, sort_order=SortOrder.ASC
        )
        names = [item.name for item in items]
        assert names.index("zzz") < names.index("aaa")

    def test_list_raises(self):
        client = make_client()
        client.file.stat = MagicMock(return_value=make_file())
        with pytest.raises(NotADirectoryError):
            client.file.list("/some/dir")

        client = make_client()
        client.file.stat = MagicMock(side_effect=FileNotFoundError("path not found"))
        with pytest.raises(FileNotFoundError):
            client.file.list("/some/dir")


class TestFind:

    @pytest.fixture(scope="class")
    def find_setup(self, api_client, shared):
        find_dir = api_client.file.create_directory(f"{shared.root_dir.path}/find")
        upload_file(api_client, find_dir.path, fname="root.bin")
        find_sub_dir = api_client.file.create_directory(f"{find_dir.path}/subfolder")
        find_sub_file = upload_file(api_client, find_sub_dir.path, fname="sub.bin")
        # Give the server a moment to index the new content
        time.sleep(2)
        api_client.register_entry(find_dir)
        api_client.register_entry(find_sub_dir)
        api_client.register_entry(find_sub_file)
        yield find_dir, find_sub_dir, find_sub_file
        api_client.unregister_entry(find_sub_file)
        api_client.unregister_entry(find_sub_dir)
        api_client.unregister_entry(find_dir)

    def test_find_in_subdirectory(self, api_client, find_setup):
        _, sub_dir, sub_file = find_setup
        entries = api_client.file.find("sub.bin", path=sub_dir.path)
        assert len(entries) == 1
        assert entries[0].id == sub_file.id
        assert entries[0].name == sub_file.name
        assert not entries[0].is_directory
        assert entries[0].parent_id == sub_dir.id
        assert entries[0].path == sub_file.path
        assert entries[0].size == sub_file.size
        assert entries[0].sha1 == sub_file.sha1

    def test_find_in_parent_directory(self, api_client, find_setup):
        dir, sub_dir, sub_file = find_setup
        entries = api_client.file.find("sub.bin", path=dir)
        assert len(entries) == 1
        assert entries[0].id == sub_file.id
        assert entries[0].name == sub_file.name
        assert not entries[0].is_directory
        assert entries[0].parent_id == sub_dir.id
        assert entries[0].path == sub_file.path
        assert entries[0].size == sub_file.size
        assert entries[0].sha1 == sub_file.sha1

    def test_find_folder(self, api_client, find_setup):
        dir, sub_dir, _ = find_setup
        entries = api_client.file.find(sub_dir.name, path=dir)
        assert len(entries) == 1
        assert entries[0].id == sub_dir.id
        assert entries[0].name == sub_dir.name
        assert entries[0].is_directory
        assert entries[0].parent_id == dir.id
        assert entries[0].path == sub_dir.path

    def test_find_not_found(self, api_client, find_setup):
        _, sub_dir, _ = find_setup
        entries = api_client.file.find("root.bin", path=sub_dir)
        assert len(entries) == 0

    def test_find_global_search(self, api_client, find_setup):
        dir, sub_dir, _ = find_setup
        entries = api_client.file.find(sub_dir.name)
        assert len(entries) == 1
        assert entries[0].id == sub_dir.id
        assert entries[0].name == sub_dir.name
        assert entries[0].parent_id == dir.id
        assert entries[0].is_directory
        assert entries[0].path == sub_dir.path

    def test_find_with_nonexistent_path(self):
        client = make_client()
        # id=0 signals the path does not exist
        client._api.fs_dir_getid.return_value = {"state": True, "id": 0}
        with pytest.raises(FileNotFoundError):
            len(client.file.find("query", path="/nonexistent"))


class TestDownloadUrl:

    def test_url_returns_valid_object(self, api_client, shared):
        info = api_client.file.url(shared.file_large.path)
        assert info.url.startswith("http")
        assert info.file_name == shared.file_large.name
        assert info.file_size == shared.file_large.size
        assert info.sha1 == shared.file_large.sha1
        assert info.referer == "https://115.com/"
        assert info.user_agent
        assert "UID" in info.cookies
        assert "CID" in info.cookies
        assert "SEID" in info.cookies
        assert "KID" in info.cookies

    def test_url_directory_raises(self):
        client = make_client()
        client.file._resolve_entry = MagicMock(return_value=make_dir())
        with pytest.raises(IsADirectoryError):
            client.file.url("/some/dir")

        client = make_client()
        client.file._resolve_entry = MagicMock(
            side_effect=FileNotFoundError("path not found")
        )
        with pytest.raises(FileNotFoundError):
            client.file.url("/some/dir")


class TestOpen:

    def test_open_read(self, api_client, shared):
        with api_client.file.open(shared.file_large) as rf:
            data = rf.read()
        sha1 = hashlib.sha1(data).hexdigest().upper()
        assert sha1 == shared.file_large.sha1
        assert len(data) == shared.file_large.size

        with api_client.file.open(shared.file_large) as rf:
            chunk1 = rf.read(100)
            assert len(chunk1) == 100
            assert rf.tell() == 100

            chunk2 = rf.read(200)
            assert len(chunk2) == 200
            assert rf.tell() == 300

        assert data[:100] == chunk1
        assert data[100:300] == chunk2

    def test_open_raises(self):
        client = make_client()
        client.file._resolve_entry = MagicMock(return_value=make_dir())
        with pytest.raises(IsADirectoryError):
            client.file.open("/some/dir")

        client = make_client()
        client.file._resolve_entry = MagicMock(
            side_effect=FileNotFoundError("path not found")
        )
        with pytest.raises(FileNotFoundError):
            client.file.open("/some/dir")
