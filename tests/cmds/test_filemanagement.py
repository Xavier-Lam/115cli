import json
import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from cli115.cli import build_parser, load_config
from cli115.client.models import (
    Directory,
    DownloadUrl,
    File,
    SortField,
)
from cli115.cmds.cp import CpCommand
from cli115.cmds.fetch import FetchCommand
from cli115.cmds.find import FindCommand
from cli115.cmds.id import IdCommand
from cli115.cmds.ls import LsCommand
from cli115.cmds.mkdir import MkdirCommand
from cli115.cmds.mv import MvCommand
from cli115.cmds.rename import RenameCommand
from cli115.cmds.rm import RmCommand
from cli115.cmds.stat import StatCommand
from cli115.cmds.upload import UploadCommand
from cli115.cmds.url import UrlCommand
from cli115.credentials import CredentialManager
from cli115.exceptions import CommandLineError
from cli115.uploader import UploadEntry
from tests.helpers import make_lazy


def _build_parser():
    cfg = load_config()
    cm = CredentialManager(cfg)
    return build_parser(cfg, cm)


def _make_dir(name="testdir", id="100", parent_id="0", file_count=5):
    return Directory(
        id=id,
        parent_id=parent_id,
        name=name,
        path=None,
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


def _make_url():
    return DownloadUrl(
        url="https://cdn.115.com/test.bin?t=123",
        file_name="test.bin",
        file_size=4096,
        sha1="A" * 40,
        user_agent="Mozilla/5.0",
        referer="https://115.com/",
        cookies="UID=u1; CID=c1; SEID=s1; KID=k1",
    )


def _make_remote_file_mock():
    mock_remote = MagicMock()
    mock_remote.__enter__ = lambda s: s
    mock_remote.__exit__ = MagicMock(return_value=False)
    mock_remote.read.side_effect = [b"x" * 1024, b""]
    return mock_remote


class TestCpCommand:
    @patch.object(CpCommand, "_create_client")
    def test_single_copy(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(["cp", "/src/file.txt", "/dst"])
        cmds["cp"].execute(args)

        mock_client.file.copy.assert_called_once_with("/src/file.txt", "/dst")
        assert "Copied" in capsys.readouterr().out

    @patch.object(CpCommand, "_create_client")
    def test_batch_copy(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(["cp", "/a", "/b", "/dst"])
        cmds["cp"].execute(args)

        mock_client.file.batch_copy.assert_called_once_with("/a", "/b", dest_dir="/dst")


class TestFetchCommand:
    def _make_client_mock(self, file=None):
        if file is None:
            file = _make_file(name="remote.bin", size=1024)
        mock_client = MagicMock()
        mock_client.file.stat.return_value = file
        mock_client.file.open.return_value = _make_remote_file_mock()
        return mock_client

    @patch.object(FetchCommand, "_create_client")
    def test_fetch_saves_file(self, mock_create, capsys):
        mock_create.return_value = self._make_client_mock()

        parser, cmds = _build_parser()
        args = parser.parse_args(["fetch", "/remote/remote.bin"])

        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = os.getcwd()
            os.chdir(tmpdir)
            try:
                cmds["fetch"].execute(args)
                assert os.path.exists("remote.bin")
                assert "remote.bin" in capsys.readouterr().out
                assert os.path.getsize("remote.bin") == 1024
                assert open("remote.bin", "rb").read() == b"x" * 1024
            finally:
                os.chdir(orig_dir)

    @patch.object(FetchCommand, "_create_client")
    def test_fetch_output_path_explicit(self, mock_create):
        mock_create.return_value = self._make_client_mock()

        parser, cmds = _build_parser()
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "custom.bin")
            args = parser.parse_args(["fetch", "/remote/remote.bin", "-o", out_path])
            cmds["fetch"].execute(args)
            assert os.path.exists(out_path)

    @patch.object(FetchCommand, "_create_client")
    def test_fetch_output_to_directory_uses_remote_name(self, mock_create):
        mock_create.return_value = self._make_client_mock()

        parser, cmds = _build_parser()
        with tempfile.TemporaryDirectory() as tmpdir:
            args = parser.parse_args(["fetch", "/remote/remote.bin", "-o", tmpdir])
            cmds["fetch"].execute(args)
            assert os.path.exists(os.path.join(tmpdir, "remote.bin"))

    @patch("cli115.cmds.fetch.sha1_file")
    @patch.object(FetchCommand, "_create_client")
    def test_fetch_check_integrity_passes(self, mock_create, mock_sha1, capsys):
        file = _make_file(name="remote.bin", size=1024)
        mock_create.return_value = self._make_client_mock(file=file)
        mock_sha1.return_value = (file.sha1, file.size)

        parser, cmds = _build_parser()
        args = parser.parse_args(["fetch", "/remote/remote.bin", "--check-integrity"])

        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = os.getcwd()
            os.chdir(tmpdir)
            try:
                cmds["fetch"].execute(args)
                assert "Checking file integrity" in capsys.readouterr().out
            finally:
                os.chdir(orig_dir)

    @patch("cli115.cmds.fetch.sha1_file")
    @patch.object(FetchCommand, "_create_client")
    def test_fetch_check_integrity_enabled_by_config(
        self, mock_create, mock_sha1, capsys
    ):
        cfg = load_config()
        cfg["download"]["check_integrity"] = "true"
        file = _make_file(name="remote.bin", size=1024)
        mock_create.return_value = self._make_client_mock(file=file)
        mock_sha1.return_value = (file.sha1, file.size)

        parser, cmds = build_parser(cfg, CredentialManager(cfg))
        args = parser.parse_args(["fetch", "/remote/remote.bin"])

        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = os.getcwd()
            os.chdir(tmpdir)
            try:
                cmds["fetch"].execute(args)
                output = capsys.readouterr().out
                assert "Checking file integrity" in output
                assert mock_sha1.called
            finally:
                os.chdir(orig_dir)

    @patch.object(FetchCommand, "_create_client")
    def test_fetch_by_id(self, mock_create, capsys):
        file = _make_file(name="remote.bin", size=1024)
        mock_client = MagicMock()
        mock_client.file.id.return_value = file
        mock_client.file.open.return_value = _make_remote_file_mock()
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(["fetch", "--id", "200"])

        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = os.getcwd()
            os.chdir(tmpdir)
            try:
                cmds["fetch"].execute(args)
                mock_client.file.id.assert_called_once_with("200")
                mock_client.file.stat.assert_not_called()
                assert os.path.exists("remote.bin")
            finally:
                os.chdir(orig_dir)

    @patch("cli115.cmds.fetch.sha1_file")
    @patch.object(FetchCommand, "_create_client")
    def test_fetch_check_integrity_failed(self, mock_create, mock_sha1):
        file = _make_file(name="remote.bin", size=1024)
        mock_create.return_value = self._make_client_mock(file=file)
        mock_sha1.return_value = (file.sha1, 512)
        parser, cmds = _build_parser()
        args = parser.parse_args(["fetch", "/remote/remote.bin", "--check-integrity"])

        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = os.getcwd()
            os.chdir(tmpdir)
            try:
                with pytest.raises(CommandLineError, match="size mismatch"):
                    cmds["fetch"].execute(args)
            finally:
                os.chdir(orig_dir)

        file = _make_file(name="remote.bin", size=1024)
        mock_create.return_value = self._make_client_mock(file=file)
        mock_sha1.return_value = ("wrong_sha1", file.size)

        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = os.getcwd()
            os.chdir(tmpdir)
            try:
                with pytest.raises(CommandLineError, match="sha1 mismatch"):
                    cmds["fetch"].execute(args)
            finally:
                os.chdir(orig_dir)


class TestFindCommand:
    def _make_client_mock(self, entries=None, total=None):
        if entries is None:
            entries = [_make_dir(), _make_file()]
        mock_client = MagicMock()
        mock_client.file.find.return_value = make_lazy(entries, total=total)
        return mock_client

    @patch.object(FindCommand, "_create_client")
    def test_find_global_search(self, mock_create, capsys):
        mock_create.return_value = self._make_client_mock()

        parser, cmds = _build_parser()
        args = parser.parse_args(["find", "--format", "json", "test"])
        cmds["find"].execute(args)

        call_kwargs = mock_create.return_value.file.find.call_args
        assert call_kwargs.kwargs["path"] is None
        assert call_kwargs.args[0] == "test"

        data = json.loads(capsys.readouterr().out)
        ids = [d["ID"] for d in data]
        assert "100" in ids
        assert "200" in ids
        names = [d["Name"] for d in data]
        assert "testdir/" in names
        assert "test.txt" in names

    @patch.object(FindCommand, "_create_client")
    def test_find_with_path(self, mock_create):
        mock_create.return_value = self._make_client_mock()

        parser, cmds = _build_parser()
        args = parser.parse_args(["find", "/docs", "keyword"])
        cmds["find"].execute(args)

        call_kwargs = mock_create.return_value.file.find.call_args
        assert call_kwargs.kwargs["path"] == "/docs"
        assert call_kwargs.args[0] == "keyword"


class TestIdCommand:
    @patch.object(IdCommand, "_create_client")
    def test_id_file(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_client.file.id.return_value = _make_file()
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(["id", "--format", "json", "200"])
        cmds["id"].execute(args)

        data = json.loads(capsys.readouterr().out)
        assert data["ID"] == "200"
        assert data["Name"] == "test.txt"
        assert data["Type"] == "File"
        assert data["SHA1"] == "abc123"
        assert data["Size"] == 1024

    @patch.object(IdCommand, "_create_client")
    def test_id_directory(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_client.file.id.return_value = _make_dir()
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(["id", "--format", "json", "100"])
        cmds["id"].execute(args)

        data = json.loads(capsys.readouterr().out)
        assert data["ID"] == "100"
        assert data["Name"] == "testdir"
        assert data["Type"] == "Directory"
        assert data["File Count"] == 5


class TestLsCommand:
    def _make_client_mock(self, entries=None, total=None):
        if entries is None:
            entries = [_make_dir(), _make_file()]
        mock_client = MagicMock()
        mock_client.file.list.return_value = make_lazy(entries, total=total)
        return mock_client

    @patch.object(LsCommand, "_create_client")
    def test_ls(self, mock_create, capsys):
        mock_create.return_value = self._make_client_mock()

        parser, cmds = _build_parser()
        args = parser.parse_args(["ls", "/"])
        cmds["ls"].execute(args)

        output = capsys.readouterr().out
        assert "testdir/" in output
        assert "test.txt" in output

        mock_create.return_value.file.list.reset_mock()
        args = parser.parse_args(["ls", "-l", "/"])
        cmds["ls"].execute(args)

        output = capsys.readouterr().out
        assert "testdir/" in output
        assert "test.txt" in output
        assert "1.0 KB" in output
        assert "dir" in output
        assert "txt" in output

    @patch.object(LsCommand, "_create_client")
    def test_ls_sort(self, mock_create):
        mock_create.return_value = self._make_client_mock()

        parser, cmds = _build_parser()
        args = parser.parse_args(["ls", "--sort", "size", "--desc", "/"])
        cmds["ls"].execute(args)

        call_kwargs = mock_create.return_value.file.list.call_args.kwargs
        assert call_kwargs["sort"] == SortField.SIZE

        mock_create.return_value.file.list.reset_mock()
        args = parser.parse_args(["ls", "--sort", "created", "/"])
        cmds["ls"].execute(args)

        call_kwargs = mock_create.return_value.file.list.call_args.kwargs
        assert call_kwargs["sort"] == SortField.CREATED_TIME

    @patch.object(LsCommand, "_create_client")
    def test_ls_sort_opened(self, mock_create):
        mock_create.return_value = self._make_client_mock()

        parser, cmds = _build_parser()
        args = parser.parse_args(["ls", "--sort", "opened", "/"])
        cmds["ls"].execute(args)

        call_kwargs = mock_create.return_value.file.list.call_args.kwargs
        assert call_kwargs["sort"] == SortField.OPEN_TIME


class TestMkdirCommand:
    @patch.object(MkdirCommand, "_create_client")
    def test_mkdir(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_client.file.create_directory.return_value = _make_dir(
            name="newdir", id="999"
        )
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(["mkdir", "--format", "json", "/newdir"])
        cmds["mkdir"].execute(args)

        mock_client.file.create_directory.assert_called_once_with(
            "/newdir", parents=False
        )
        data = json.loads(capsys.readouterr().out)
        assert data["ID"] == "999"

        mock_client.file.create_directory.reset_mock()
        args = parser.parse_args(["mkdir", "-p", "/a/b/c"])
        cmds["mkdir"].execute(args)

        mock_client.file.create_directory.assert_called_once_with(
            "/a/b/c", parents=True
        )


class TestMvCommand:
    @patch.object(MvCommand, "_create_client")
    def test_single_move(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(["mv", "/src/file.txt", "/dst"])
        cmds["mv"].execute(args)

        mock_client.file.move.assert_called_once_with("/src/file.txt", "/dst")

    @patch.object(MvCommand, "_create_client")
    def test_batch_move(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(["mv", "/a", "/b", "/dst"])
        cmds["mv"].execute(args)

        mock_client.file.batch_move.assert_called_once_with("/a", "/b", dest_dir="/dst")


class TestRenameCommand:
    @patch.object(RenameCommand, "_create_client")
    def test_rename(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(["rename", "/src/file.txt", "new-file.txt"])
        cmds["rename"].execute(args)

        mock_client.file.rename.assert_called_once_with("/src/file.txt", "new-file.txt")
        assert "Renamed: /src/file.txt -> new-file.txt" in capsys.readouterr().out


class TestRmCommand:
    @patch.object(RmCommand, "_create_client")
    def test_single_delete(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(["rm", "/file.txt"])
        cmds["rm"].execute(args)

        mock_client.file.delete.assert_called_once_with("/file.txt", recursive=False)

    @patch.object(RmCommand, "_create_client")
    def test_recursive_delete(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(["rm", "-r", "/dir"])
        cmds["rm"].execute(args)

        mock_client.file.delete.assert_called_once_with("/dir", recursive=True)

    @patch.object(RmCommand, "_create_client")
    def test_batch_delete(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(["rm", "/a", "/b"])
        cmds["rm"].execute(args)

        mock_client.file.batch_delete.assert_called_once_with(
            "/a", "/b", recursive=False
        )


class TestStatCommand:
    @patch.object(StatCommand, "_create_client")
    def test_stat_file(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_client.file.stat.return_value = _make_file()
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(["stat", "--format", "json", "/test.txt"])
        cmds["stat"].execute(args)

        data = json.loads(capsys.readouterr().out)
        assert data["ID"] == "200"
        assert data["Name"] == "test.txt"
        assert data["Type"] == "File"
        assert data["SHA1"] == "abc123"
        assert data["Size"] == 1024

    @patch.object(StatCommand, "_create_client")
    def test_stat_directory(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_client.file.stat.return_value = _make_dir()
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(["stat", "--format", "json", "/testdir"])
        cmds["stat"].execute(args)

        data = json.loads(capsys.readouterr().out)
        assert data["ID"] == "100"
        assert data["Name"] == "testdir"
        assert data["Type"] == "Directory"
        assert data["File Count"] == 5


class TestUploadCommand:
    @patch("cli115.cmds.upload.Uploader.upload")
    @patch.object(UploadCommand, "_create_client")
    def test_upload_calls_tool(self, mock_create, mock_upload):
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        mock_upload.return_value = _make_file(name="uploaded.txt")

        parser, cmds = _build_parser()
        args = parser.parse_args(
            ["upload", "--format", "json", "/local/file.txt", "/remote/file.txt"]
        )
        cmds["upload"].execute(args)

        mock_upload.assert_called_once_with(
            "/local/file.txt",
            "/remote/file.txt",
            instant_only=None,
            include=None,
            exclude=None,
            no_target_dir=False,
        )

    @patch("cli115.cmds.upload.Uploader.upload")
    @patch.object(UploadCommand, "_create_client")
    def test_upload_output(self, mock_create, mock_upload, capsys):
        mock_create.return_value = MagicMock()
        mock_upload.return_value = _make_file(name="uploaded.txt", size=2048)

        parser, cmds = _build_parser()
        args = parser.parse_args(
            ["upload", "-s", "--format", "json", "/local/file.txt", "/remote/file.txt"]
        )
        cmds["upload"].execute(args)

        data = json.loads(capsys.readouterr().out)
        assert data["ID"] == "200"
        assert data["Name"] == "uploaded.txt"
        assert data["SHA1"] == "abc123"
        assert data["Size"] == 2048

    @patch("cli115.cmds.upload.Uploader.upload")
    @patch.object(UploadCommand, "_create_client")
    def test_instant_only_passes_threshold(self, mock_create, mock_upload):
        mock_create.return_value = MagicMock()
        mock_upload.return_value = _make_file()

        parser, cmds = _build_parser()
        args = parser.parse_args(
            [
                "upload",
                "--instant-only",
                "100MB",
                "/local/file.txt",
                "/remote/file.txt",
            ]
        )
        cmds["upload"].execute(args)

        call_kwargs = mock_upload.call_args.kwargs
        assert call_kwargs["instant_only"] == 100 * 1024 * 1024

    @patch("cli115.cmds.upload.Uploader.upload")
    @patch.object(UploadCommand, "_create_client")
    def test_include_and_exclude_patterns_passed(self, mock_create, mock_upload):
        mock_create.return_value = MagicMock()
        mock_upload.return_value = _make_file()

        parser, cmds = _build_parser()
        args = parser.parse_args(
            [
                "upload",
                "--include",
                "src/**",
                "--exclude",
                "**/*.log",
                "--exclude",
                "temp/**",
                "/local/dir",
                "/remote/dir",
            ]
        )
        cmds["upload"].execute(args)

        call_kwargs = mock_upload.call_args.kwargs
        assert call_kwargs["include"] == ["src/**"]
        assert call_kwargs["exclude"] == ["**/*.log", "temp/**"]

    @patch("cli115.cmds.upload.Uploader.upload")
    @patch.object(UploadCommand, "_create_client")
    def test_upload_dir_to_file_raises_command_error(self, mock_create, mock_upload):
        mock_create.return_value = MagicMock()
        mock_upload.side_effect = FileExistsError(
            "cannot upload directory to a file path"
        )

        parser, cmds = _build_parser()
        args = parser.parse_args(["upload", "/local/dir", "/remote/file.txt"])
        with pytest.raises(FileExistsError, match="cannot upload directory"):
            cmds["upload"].execute(args)

    @patch("cli115.cmds.upload.Uploader")
    @patch.object(UploadCommand, "_create_client")
    def test_dry_run_passed_to_uploader(self, mock_create, mock_uploader_cls):
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        mock_uploader_cls.return_value.upload.return_value = None

        parser, cmds = _build_parser()
        args = parser.parse_args(
            ["upload", "--dry-run", "/local/file.txt", "/remote/file.txt"]
        )
        cmds["upload"].execute(args)

        mock_uploader_cls.assert_called_once_with(mock_client, dry_run=True)

    @patch.object(UploadCommand, "_create_client")
    def test_plan_flag_shows_plan(self, mock_create, tmp_path, capsys):
        local_file = tmp_path / "file.txt"
        local_file.write_text("content")

        mock_client = MagicMock()
        mock_client.file.stat.side_effect = FileNotFoundError("not found")
        mock_client.file.upload.return_value = None
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(
            ["upload", "--plan", str(local_file), "/remote/file.txt"]
        )
        cmds["upload"].execute(args)

        output = capsys.readouterr().out
        assert str(local_file) in output
        assert "/remote/file.txt" in output

    @patch.object(UploadCommand, "_create_client")
    def test_dry_run_flag_shows_plan(self, mock_create, tmp_path, capsys):
        local_file = tmp_path / "file.txt"
        local_file.write_text("content")

        mock_client = MagicMock()
        mock_client.file.stat.side_effect = FileNotFoundError("not found")
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(
            ["upload", "--dry-run", str(local_file), "/remote/file.txt"]
        )
        cmds["upload"].execute(args)

        output = capsys.readouterr().out
        assert str(local_file) in output
        assert "/remote/file.txt" in output

    @patch("cli115.cmds.upload.Uploader")
    @patch.object(UploadCommand, "_create_client")
    def test_warns_failed_files_after_upload(
        self, mock_create, mock_uploader_cls, capsys
    ):
        mock_create.return_value = MagicMock()

        mock_uploader = mock_uploader_cls.return_value
        mock_uploader.upload.return_value = None

        failed_a = UploadEntry("/local/a.txt", "/remote/a.txt")
        failed_a.error = RuntimeError("network timeout")
        failed_b = UploadEntry("/local/b.txt", "/remote/b.txt")
        failed_b.error = ValueError("checksum mismatch")
        mock_uploader.entries = [failed_a, failed_b]

        parser, cmds = _build_parser()
        args = parser.parse_args(["upload", "-s", "/local/dir", "/remote/dir"])
        cmds["upload"].execute(args)

        stderr = capsys.readouterr().err
        assert "2 file(s) failed to upload" in stderr
        assert "/local/a.txt -> /remote/a.txt: network timeout" in stderr
        assert "/local/b.txt -> /remote/b.txt: checksum mismatch" in stderr


class TestUrlCommand:
    @patch.object(UrlCommand, "_create_client")
    def test_aria2c_output(self, mock_create, capsys):
        cfg = load_config()
        cfg["download"] = {"min_split_size": "2M", "max_connection": "10"}
        mock_client = MagicMock()
        mock_client.file.url.return_value = _make_url()
        mock_create.return_value = mock_client

        parser, cmds = build_parser(cfg, CredentialManager(cfg))
        args = parser.parse_args(["url", "--format", "aria2c", "/test.bin"])
        cmds["url"].execute(args)

        output = capsys.readouterr().out
        assert "aria2c" in output
        assert "-o" in output
        assert "test.bin" in output
        assert "-k2M" in output
        assert "-x10" in output
        assert "-s10" in output
        assert "--checksum" not in output
        assert "User-Agent: Mozilla/5.0" in output
        assert "UID=u1" in output
        assert "https://cdn.115.com/test.bin?t=123" in output

    @patch.object(UrlCommand, "_create_client")
    def test_aria2c_check_integrity_enabled_by_config(self, mock_create, capsys):
        cfg = load_config()
        cfg["download"] = {
            "min_split_size": "2M",
            "max_connection": "10",
            "check_integrity": "true",
        }
        mock_client = MagicMock()
        mock_client.file.url.return_value = _make_url()
        mock_create.return_value = mock_client

        parser, cmds = build_parser(cfg, CredentialManager(cfg))
        args = parser.parse_args(["url", "--format", "aria2c", "/test.bin"])
        cmds["url"].execute(args)

        output = capsys.readouterr().out
        assert f"--checksum=sha-1={_make_url().sha1}" in output

    @patch.object(UrlCommand, "_create_client")
    def test_aria2c_with_check_integrity(self, mock_create, capsys):
        cfg = load_config()
        cfg["download"] = {"min_split_size": "2M", "max_connection": "10"}
        mock_client = MagicMock()
        mock_client.file.url.return_value = _make_url()
        mock_create.return_value = mock_client

        parser, cmds = build_parser(cfg, CredentialManager(cfg))
        args = parser.parse_args(
            ["url", "--format", "aria2c", "--check-integrity", "/test.bin"]
        )
        cmds["url"].execute(args)

        output = capsys.readouterr().out
        assert f"--checksum=sha-1={_make_url().sha1}" in output
