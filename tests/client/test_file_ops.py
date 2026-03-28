import uuid

import pytest

from cli115.exceptions import AlreadyExistsError, DirectoryNotEmptyError
from tests.client.conftest import upload_file


class TestCreateDirectory:

    def test_create_directory(self, api_client, root_dir):
        name = "cdir"
        path = f"{root_dir.path}/{name}"
        folder = api_client.file.create_directory(path)
        assert folder.id
        assert folder.name == name
        assert folder.path == path

        items = api_client.file.list(root_dir)
        names = {item.name for item in items}
        assert name in names

    def test_create_existing_directory_raises(self, api_client, shared):
        with pytest.raises(AlreadyExistsError):
            api_client.file.create_directory(shared.dir_a.path)

    def test_create_directory_with_nonexistent_parent(self, api_client, root_dir):
        parent_name = "cdir_np"
        child_name = "child"
        path = f"{root_dir.path}/{parent_name}/{child_name}"
        folder = api_client.file.create_directory(path, parents=True)
        assert folder.name == child_name
        assert folder.path == path
        items = api_client.file.list(f"{root_dir.path}/{parent_name}")
        assert len(items) == 1
        assert items[0].name == child_name


class TestDelete:

    def test_delete_directory(self, api_client, root_dir):
        name = "deld"
        directory = api_client.file.create_directory(f"{root_dir.path}/{name}")
        api_client.file.delete(f"{root_dir.path}/{name}")
        items = api_client.file.list(root_dir)
        ids = {item.id for item in items}
        names = {item.name for item in items}
        assert directory.id not in ids
        assert name not in names

    def test_delete_file(self, api_client, root_dir):
        entry = upload_file(api_client, root_dir.path)
        api_client.file.delete(entry.path)
        items = api_client.file.list(root_dir)
        ids = {item.id for item in items}
        names = {item.name for item in items}
        assert entry.id not in ids
        assert entry.name not in names

    def test_batch_delete(self, api_client, root_dir):
        name1 = "bdel1"
        name2 = "bdel2"
        dir1 = api_client.file.create_directory(f"{root_dir.path}/{name1}")
        dir2 = api_client.file.create_directory(f"{root_dir.path}/{name2}")
        api_client.file.batch_delete(
            f"{root_dir.path}/{name1}",
            f"{root_dir.path}/{name2}",
        )
        items = api_client.file.list(root_dir)
        ids = {item.id for item in items}
        names = {item.name for item in items}
        assert dir1.id not in ids
        assert dir2.id not in ids
        assert name1 not in names
        assert name2 not in names

    def test_delete_recursive(self, api_client, root_dir):
        name = "del_nonempty"
        dir_path = f"{root_dir.path}/{name}"
        directory = api_client.file.create_directory(dir_path)
        api_client.file.create_directory(f"{dir_path}/inner")
        with pytest.raises(DirectoryNotEmptyError):
            api_client.file.delete(dir_path, recursive=False)

        api_client.file.delete(dir_path, recursive=True)
        items = api_client.file.list(root_dir)
        assert directory.id not in {item.id for item in items}
        assert name not in {i.name for i in items}


class TestMove:

    def test_move_directory(self, api_client, shared):
        src_path = shared.dir_a.path
        dest_path = shared.dir_b.path

        child = "move_child_dir"
        directory = api_client.file.create_directory(f"{src_path}/{child}")
        api_client.file.move(f"{src_path}/{child}", dest_path)
        dest_entries = api_client.file.list(dest_path)
        src_entries = api_client.file.list(src_path)
        src_names = {i.name for i in src_entries}
        assert directory.id in {i.id for i in dest_entries}
        assert child in {i.name for i in dest_entries}
        assert directory.id not in {i.id for i in src_entries}
        assert child not in src_names

    def test_move_file(self, api_client, shared):
        src_path = shared.dir_a.path
        dest_path = shared.dir_b.path

        entry = upload_file(api_client, src_path)
        api_client.file.move(entry.path, dest_path)
        dest_entries = api_client.file.list(dest_path)
        src_entries = api_client.file.list(src_path)
        assert entry.name in {i.name for i in dest_entries}
        assert entry.id in {i.id for i in dest_entries}
        assert entry.name not in {i.name for i in src_entries}
        assert entry.id not in {i.id for i in src_entries}

    def test_batch_move(self, api_client, shared):
        src_path = shared.dir_a.path
        dest_path = shared.dir_b.path

        directory = api_client.file.create_directory(f"{src_path}/batch_move_1")
        entry = upload_file(api_client, src_path, fname="batch_move_2.bin")
        api_client.file.batch_move(
            f"{src_path}/batch_move_1",
            f"{src_path}/batch_move_2.bin",
            dest_dir=dest_path,
        )
        dest_entries = api_client.file.list(dest_path)
        src_items = api_client.file.list(src_path)
        assert "batch_move_1" in {i.name for i in dest_entries}
        assert "batch_move_2.bin" in {i.name for i in dest_entries}
        assert directory.id in {i.id for i in dest_entries}
        assert entry.id in {i.id for i in dest_entries}
        assert "batch_move_1" not in {i.name for i in src_items}
        assert "batch_move_2.bin" not in {i.name for i in src_items}
        assert directory.id not in {i.id for i in src_items}
        assert entry.id not in {i.id for i in src_items}


class TestCopy:

    def test_copy_directory(self, api_client, shared):
        src_path = shared.dir_a.path
        dest_path = shared.dir_b.path

        child = "copy_child_dir"
        directory = api_client.file.create_directory(f"{src_path}/{child}")
        api_client.file.copy(f"{src_path}/{child}", dest_path)
        dest_entries = api_client.file.list(dest_path)
        src_entries = api_client.file.list(src_path)
        assert directory.id not in {i.id for i in dest_entries}
        assert directory.id in {i.id for i in src_entries}
        assert child in {i.name for i in dest_entries}
        assert child in {i.name for i in src_entries}

    def test_copy_file(self, api_client, shared):
        src_path = shared.dir_a.path
        dest_path = shared.dir_b.path

        entry = upload_file(api_client, src_path)
        api_client.file.copy(entry.path, dest_path)
        dest_entries = api_client.file.list(dest_path)
        src_entries = api_client.file.list(src_path)
        assert entry.name in {i.name for i in dest_entries}
        assert entry.id not in {i.id for i in dest_entries}
        assert entry.name in {i.name for i in src_entries}
        assert entry.id in {i.id for i in src_entries}

    def test_batch_copy(self, api_client, shared):
        src_path = shared.dir_a.path
        dest_path = shared.dir_b.path

        directory = api_client.file.create_directory(f"{src_path}/batch_copy_1")
        entry = upload_file(api_client, src_path, fname="batch_copy_2.bin")
        api_client.file.batch_copy(
            f"{src_path}/batch_copy_1",
            f"{src_path}/batch_copy_2.bin",
            dest_dir=dest_path,
        )
        dest_items = api_client.file.list(dest_path)
        assert "batch_copy_1" in {i.name for i in dest_items}
        assert "batch_copy_2.bin" in {i.name for i in dest_items}
        assert directory.id not in {i.id for i in dest_items}
        assert entry.id not in {i.id for i in dest_items}
        src_items = api_client.file.list(src_path)
        assert "batch_copy_1" in {i.name for i in src_items}
        assert "batch_copy_2.bin" in {i.name for i in src_items}
        assert directory.id in {i.id for i in src_items}
        assert entry.id in {i.id for i in src_items}


class TestRename:

    def test_rename_directory(self, api_client, root_dir):
        old_name = "rend"
        new_name = "rend_new"
        directory = api_client.file.create_directory(f"{root_dir.path}/{old_name}")
        api_client.file.rename(f"{root_dir.path}/{old_name}", new_name)
        result = api_client.file.stat(f"{root_dir.path}/{new_name}")
        assert result.id == directory.id
        assert result.name == new_name

    def test_rename_file(self, api_client, root_dir):
        entry = upload_file(api_client, root_dir.path)
        new_name = f"renf_new_{uuid.uuid4().hex[:8]}.bin"
        api_client.file.rename(entry.path, new_name)
        result = api_client.file.stat(f"{root_dir.path}/{new_name}")
        assert result.id == entry.id
        assert result.name == new_name
