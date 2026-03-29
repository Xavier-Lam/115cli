from unittest.mock import MagicMock

import pytest

from cli115.tools import upload
from tests.client.conftest import make_dir, make_file


def _make_client():
    mock = MagicMock()
    mock.file.upload.return_value = make_file()
    return mock


class TestUploadFile:
    def test_upload_to_nonexistent_path(self):
        client = _make_client()
        client.file.stat.side_effect = FileNotFoundError("not found")
        uploaded = make_file(name="file.txt")
        client.file.upload.return_value = uploaded

        result = upload(client, "/local/file.txt", "/remote/file.txt")

        client.file.upload.assert_called_once_with(
            "/remote/file.txt", "/local/file.txt", instant_only=None
        )
        assert result is uploaded

    def test_upload_to_existing_directory_appends_filename(self):
        client = _make_client()
        client.file.stat.return_value = make_dir(name="remotedir")
        uploaded = make_file(name="file.txt")
        client.file.upload.return_value = uploaded

        result = upload(client, "/local/path/file.txt", "/remote/dir")

        client.file.upload.assert_called_once_with(
            "/remote/dir/file.txt", "/local/path/file.txt", instant_only=None
        )
        assert result is uploaded

    def test_upload_instant_only_threshold_passed_through(self):
        client = _make_client()
        client.file.stat.side_effect = FileNotFoundError("not found")
        threshold = 100 * 1024 * 1024  # 100 MB

        upload(client, "/local/file.txt", "/remote/file.txt", instant_only=threshold)

        client.file.upload.assert_called_once_with(
            "/remote/file.txt", "/local/file.txt", instant_only=threshold
        )


class TestUploadDirectory:
    def test_upload_dir_to_nonexistent_remote_creates_it(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")

        client = _make_client()
        client.file.stat.side_effect = FileNotFoundError("not found")
        dest_dir = make_dir(name=tmp_path.name)
        client.file.create_directory.return_value = dest_dir

        result = upload(client, str(tmp_path), "/remote/newdir")

        client.file.create_directory.assert_called_once_with(
            "/remote/newdir", parents=True
        )
        assert result is dest_dir

    def test_upload_dir_to_existing_remote_dir_creates_subdir(self, tmp_path):
        (tmp_path / "file.txt").write_text("content")

        client = _make_client()
        client.file.stat.return_value = make_dir(name="existing")
        dest_dir = make_dir(name=tmp_path.name)
        client.file.create_directory.return_value = dest_dir

        result = upload(client, str(tmp_path), "/remote/existing")

        expected_dest = "/remote/existing/" + tmp_path.name
        client.file.create_directory.assert_called_once_with(expected_dest)
        assert result is dest_dir

    def test_upload_dir_to_remote_file_raises(self, tmp_path):
        (tmp_path / "file.txt").write_text("content")

        client = _make_client()
        client.file.stat.return_value = make_file(name="remote.txt")

        with pytest.raises(FileExistsError, match="cannot upload directory"):
            upload(client, str(tmp_path), "/remote/file.txt")

        client.file.upload.assert_not_called()

    def test_upload_dir_all_files_are_uploaded(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "c.txt").write_text("c")

        client = _make_client()
        client.file.stat.side_effect = FileNotFoundError("not found")
        client.file.create_directory.return_value = make_dir()

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
        client.file.stat.side_effect = FileNotFoundError("not found")
        client.file.create_directory.return_value = make_dir()

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
        client.file.stat.side_effect = FileNotFoundError("not found")
        client.file.create_directory.return_value = make_dir()
        threshold = 50 * 1024 * 1024  # 50 MB

        upload(client, str(tmp_path), "/remote/dest", instant_only=threshold)

        client.file.upload.assert_called_once()
        assert client.file.upload.call_args.kwargs["instant_only"] == threshold


class TestUploadDirectoryPatterns:
    def test_exclude_pattern_filters_files(self, tmp_path):
        (tmp_path / "app.py").write_text("code")
        (tmp_path / "debug.log").write_text("log")
        (tmp_path / "error.log").write_text("log")

        client = _make_client()
        client.file.stat.side_effect = FileNotFoundError("not found")
        client.file.create_directory.return_value = make_dir()

        upload(client, str(tmp_path), "/remote/dest", exclude=["**/*.log"])

        client.file.create_directory.assert_called_once_with(
            "/remote/dest", parents=True
        )
        assert client.file.upload.call_count == 1
        uploaded_name = client.file.upload.call_args.args[0].rsplit("/", 1)[-1]
        assert uploaded_name == "app.py"

    def test_include_pattern_filters_files(self, tmp_path):
        (tmp_path / "main.py").write_text("code")
        (tmp_path / "utils.py").write_text("code")
        (tmp_path / "README.md").write_text("docs")

        client = _make_client()
        client.file.stat.side_effect = FileNotFoundError("not found")
        client.file.create_directory.return_value = make_dir()

        upload(client, str(tmp_path), "/remote/dest", include=["**/*.py"])

        client.file.create_directory.assert_called_once_with(
            "/remote/dest", parents=True
        )
        assert client.file.upload.call_count == 2
        uploaded_names = {
            c.args[0].rsplit("/", 1)[-1] for c in client.file.upload.call_args_list
        }
        assert uploaded_names == {"main.py", "utils.py"}

    def test_exclude_subdirectory_pattern(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("code")
        temp = tmp_path / "temp"
        temp.mkdir()
        (temp / "cache.bin").write_text("cache")

        client = _make_client()
        client.file.stat.side_effect = FileNotFoundError("not found")
        client.file.create_directory.return_value = make_dir()

        upload(client, str(tmp_path), "/remote/dest", exclude=["temp/**"])

        created_dirs = [c.args[0] for c in client.file.create_directory.call_args_list]
        assert "/remote/dest" in created_dirs
        assert "/remote/dest/src" in created_dirs
        assert not any("temp" in p for p in created_dirs)
        assert client.file.upload.call_count == 1
        uploaded_name = client.file.upload.call_args.args[0].rsplit("/", 1)[-1]
        assert uploaded_name == "main.py"

    def test_include_and_exclude_combined(self, tmp_path):
        (tmp_path / "keep.py").write_text("code")
        (tmp_path / "skip_test.py").write_text("test code")
        (tmp_path / "data.csv").write_text("data")

        client = _make_client()
        client.file.stat.side_effect = FileNotFoundError("not found")
        client.file.create_directory.return_value = make_dir()

        upload(
            client,
            str(tmp_path),
            "/remote/dest",
            include=["**/*.py"],
            exclude=["**/skip_*"],
        )

        client.file.create_directory.assert_called_once_with(
            "/remote/dest", parents=True
        )
        assert client.file.upload.call_count == 1
        uploaded_name = client.file.upload.call_args.args[0].rsplit("/", 1)[-1]
        assert uploaded_name == "keep.py"

    def test_no_patterns_uploads_all(self, tmp_path):
        (tmp_path / "a.py").write_text("a")
        (tmp_path / "b.log").write_text("b")

        client = _make_client()
        client.file.stat.side_effect = FileNotFoundError("not found")
        client.file.create_directory.return_value = make_dir()

        upload(client, str(tmp_path), "/remote/dest")

        client.file.create_directory.assert_called_once_with(
            "/remote/dest", parents=True
        )
        assert client.file.upload.call_count == 2
