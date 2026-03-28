from datetime import datetime
from unittest.mock import MagicMock

import pytest

from cli115.client.models import Directory, File
from cli115.exceptions import AlreadyExistsError, NotFoundError
from cli115.tools import upload


def _make_dir(name="testdir", id="100", parent_id="0", file_count=0):
    return Directory(
        id=id,
        parent_id=parent_id,
        name=name,
        path=f"/{name}",
        pickcode="pc1",
        created_time=datetime(2025, 1, 1),
        modified_time=datetime(2025, 6, 1),
        open_time=None,
        file_count=file_count,
    )


def _make_file(name="test.txt", id="200", parent_id="100", size=1024):
    return File(
        id=id,
        parent_id=parent_id,
        name=name,
        path=None,
        pickcode="pc2",
        created_time=datetime(2025, 1, 1),
        modified_time=datetime(2025, 6, 1),
        open_time=None,
        size=size,
        sha1="abc123",
        file_type="txt",
        starred=False,
    )


def _make_client():
    mock = MagicMock()
    mock.file.upload.return_value = _make_file()
    return mock


class TestUploadFile:
    def test_upload_to_nonexistent_path(self):
        client = _make_client()
        client.file.stat.side_effect = NotFoundError("not found")
        uploaded = _make_file(name="file.txt")
        client.file.upload.return_value = uploaded

        result = upload(client, "/local/file.txt", "/remote/file.txt")

        client.file.upload.assert_called_once_with(
            "/remote/file.txt", "/local/file.txt", instant_only=False
        )
        assert result is uploaded

    def test_upload_to_existing_directory_appends_filename(self):
        client = _make_client()
        client.file.stat.return_value = _make_dir(name="remotedir")
        uploaded = _make_file(name="file.txt")
        client.file.upload.return_value = uploaded

        result = upload(client, "/local/path/file.txt", "/remote/dir")

        client.file.upload.assert_called_once_with(
            "/remote/dir/file.txt", "/local/path/file.txt", instant_only=False
        )
        assert result is uploaded

    def test_upload_instant_only_flag_passed_through(self):
        client = _make_client()
        client.file.stat.side_effect = NotFoundError("not found")

        upload(client, "/local/file.txt", "/remote/file.txt", instant_only=True)

        client.file.upload.assert_called_once_with(
            "/remote/file.txt", "/local/file.txt", instant_only=True
        )


class TestUploadDirectory:
    def test_upload_dir_to_nonexistent_remote_creates_it(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")

        client = _make_client()
        client.file.stat.side_effect = NotFoundError("not found")
        dest_dir = _make_dir(name=tmp_path.name)
        client.file.create_directory.return_value = dest_dir

        result = upload(client, str(tmp_path), "/remote/newdir")

        client.file.create_directory.assert_called_once_with(
            "/remote/newdir", parents=True
        )
        assert result is dest_dir

    def test_upload_dir_to_existing_remote_dir_creates_subdir(self, tmp_path):
        (tmp_path / "file.txt").write_text("content")

        client = _make_client()
        client.file.stat.return_value = _make_dir(name="existing")
        dest_dir = _make_dir(name=tmp_path.name)
        client.file.create_directory.return_value = dest_dir

        result = upload(client, str(tmp_path), "/remote/existing")

        expected_dest = "/remote/existing/" + tmp_path.name
        client.file.create_directory.assert_called_once_with(expected_dest)
        assert result is dest_dir

    def test_upload_dir_to_remote_file_raises(self, tmp_path):
        (tmp_path / "file.txt").write_text("content")

        client = _make_client()
        client.file.stat.return_value = _make_file(name="remote.txt")

        with pytest.raises(AlreadyExistsError, match="Cannot upload directory"):
            upload(client, str(tmp_path), "/remote/file.txt")

        client.file.upload.assert_not_called()

    def test_upload_dir_all_files_are_uploaded(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "c.txt").write_text("c")

        client = _make_client()
        client.file.stat.side_effect = NotFoundError("not found")
        client.file.create_directory.return_value = _make_dir()

        upload(client, str(tmp_path), "/remote/dest")

        assert client.file.upload.call_count == 3
        uploaded_names = {
            c.args[0].rsplit("/", 1)[-1] for c in client.file.upload.call_args_list
        }
        assert uploaded_names == {"a.txt", "b.txt", "c.txt"}

    def test_upload_dir_multilevel_subdirs_created(self, tmp_path):
        # Structure:
        #   tmp/
        #     root.txt
        #     sub1/
        #       mid.txt
        #       sub2/
        #         deep.txt
        (tmp_path / "root.txt").write_text("root")
        sub1 = tmp_path / "sub1"
        sub1.mkdir()
        (sub1 / "mid.txt").write_text("mid")
        sub2 = sub1 / "sub2"
        sub2.mkdir()
        (sub2 / "deep.txt").write_text("deep")

        client = _make_client()
        client.file.stat.side_effect = NotFoundError("not found")
        client.file.create_directory.return_value = _make_dir()

        upload(client, str(tmp_path), "/remote/dest")

        # Base dir + sub1 + sub1/sub2
        assert client.file.create_directory.call_count == 3
        create_paths = [c.args[0] for c in client.file.create_directory.call_args_list]
        assert "/remote/dest" in create_paths
        assert any("sub1" in p for p in create_paths)
        assert any("sub2" in p for p in create_paths)

        # All 3 files uploaded
        assert client.file.upload.call_count == 3
        uploaded_names = {
            c.args[0].rsplit("/", 1)[-1] for c in client.file.upload.call_args_list
        }
        assert uploaded_names == {"root.txt", "mid.txt", "deep.txt"}

    def test_upload_dir_instant_only_passed_to_file_uploads(self, tmp_path):
        (tmp_path / "file.txt").write_text("content")

        client = _make_client()
        client.file.stat.side_effect = NotFoundError("not found")
        client.file.create_directory.return_value = _make_dir()

        upload(client, str(tmp_path), "/remote/dest", instant_only=True)

        client.file.upload.assert_called_once()
        assert client.file.upload.call_args.kwargs["instant_only"] is True
