from configparser import ConfigParser
import io
import unittest
from datetime import datetime
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

from cli115.cli import load_config, main
from cli115.client.base import DEFAULT_PAGE_SIZE
from cli115.client.lazy import LazyCollection
from cli115.client.models import (
    CloudTask,
    Directory,
    DownloadUrl,
    DownloadQuota,
    File,
    Pagination,
    SortField,
    TaskStatus,
)
from cli115.cmds.cp import CpCommand
from cli115.cmds.download import (
    DownloadAddCommand,
    DownloadCommand,
    DownloadDeleteCommand,
    DownloadListCommand,
    DownloadQuotaCommand,
)
from cli115.cmds.fetch import FetchCommand
from cli115.cmds.find import FindCommand
from cli115.cmds.id import IdCommand
from cli115.cmds.ls import LsCommand
from cli115.cmds.mkdir import MkdirCommand
from cli115.cmds.mv import MvCommand
from cli115.cmds.rm import RmCommand
from cli115.cmds.stat import StatCommand
from cli115.cmds.upload import UploadCommand
from cli115.cmds.url import UrlCommand
from cli115.credentials import CredentialManager
from cli115.exceptions import NotFoundError


def build_parser(
    config: ConfigParser = None,
    credential_manager: CredentialManager = None,
) -> ConfigParser:
    from cli115.cli import build_parser

    config = config or load_config()
    credential_manager = credential_manager or CredentialManager(config)
    return build_parser(config, credential_manager)


def _make_lazy(items, total=None):
    if total is None:
        total = len(items)
    pagination = Pagination(total=total, offset=0, limit=len(items) if items else 115)

    def fetch(page, page_size):
        offset = (page - 1) * page_size
        sliced = items[offset : offset + page_size]
        pg = Pagination(total=total, offset=offset, limit=page_size)
        return sliced, pg

    col = LazyCollection(fetch, page_size=len(items) if items else 115)
    # pre-warm first page so tests don't need network
    if items:
        col._ensure_page(1)
    else:
        col._pagination = pagination
    return col


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


class TestLsCommand(unittest.TestCase):
    def _make_client_mock(self, entries=None, total=None):
        if entries is None:
            entries = [_make_dir(), _make_file()]
        mock_client = MagicMock()
        mock_client.file.list.return_value = _make_lazy(entries, total=total)
        return mock_client

    @patch.object(LsCommand, "_create_client")
    def test_ls_short(self, mock_create):
        mock_create.return_value = self._make_client_mock()
        parser, _ = build_parser()
        args = parser.parse_args(["ls", "/"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            LsCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("testdir/", output)
        self.assertIn("test.txt", output)

    @patch.object(LsCommand, "_create_client")
    def test_ls_long(self, mock_create):
        mock_create.return_value = self._make_client_mock()
        parser, _ = build_parser()
        args = parser.parse_args(["ls", "-l", "/"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            LsCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("testdir/", output)
        self.assertIn("test.txt", output)
        # Human-readable size always shown
        self.assertIn("1.0 KB", output)
        # Type column: dir for directory, file_type for file
        self.assertIn("dir", output)
        self.assertIn("txt", output)
        self.assertIn("100", output)  # directory id
        self.assertIn("200", output)  # file id

    @patch.object(LsCommand, "_create_client")
    def test_ls_pagination_args(self, mock_create):
        mock_create.return_value = self._make_client_mock()
        parser, _ = build_parser()
        args = parser.parse_args(["ls", "--offset", "0", "--limit", "10", "/"])

        with patch("sys.stdout", new_callable=io.StringIO):
            LsCommand().execute(args)

        mock_create.return_value.file.list.assert_called_once()
        call_args = mock_create.return_value.file.list.call_args
        self.assertEqual(call_args.args[0], "/")

    @patch.object(LsCommand, "_create_client")
    def test_ls_sort_options(self, mock_create):
        mock_create.return_value = self._make_client_mock()
        parser, _ = build_parser()
        args = parser.parse_args(["ls", "--sort", "size", "--desc", "/"])

        with patch("sys.stdout", new_callable=io.StringIO):
            LsCommand().execute(args)

        call_kwargs = mock_create.return_value.file.list.call_args.kwargs
        self.assertEqual(call_kwargs["sort"], SortField.SIZE)

    @patch.object(LsCommand, "_create_client")
    def test_ls_sort_created(self, mock_create):
        mock_create.return_value = self._make_client_mock()
        parser, _ = build_parser()
        args = parser.parse_args(["ls", "--sort", "created", "/"])

        with patch("sys.stdout", new_callable=io.StringIO):
            LsCommand().execute(args)

        call_kwargs = mock_create.return_value.file.list.call_args.kwargs
        self.assertEqual(call_kwargs["sort"], SortField.CREATED_TIME)

    @patch.object(LsCommand, "_create_client")
    def test_ls_sort_opened(self, mock_create):
        mock_create.return_value = self._make_client_mock()
        parser, _ = build_parser()
        args = parser.parse_args(["ls", "--sort", "opened", "/"])

        with patch("sys.stdout", new_callable=io.StringIO):
            LsCommand().execute(args)

        call_kwargs = mock_create.return_value.file.list.call_args.kwargs
        self.assertEqual(call_kwargs["sort"], SortField.OPEN_TIME)

    @patch.object(LsCommand, "_create_client")
    def test_ls_warning_when_total_exceeds_default(self, mock_create):
        entries = [_make_dir(), _make_file()]
        mock_create.return_value = self._make_client_mock(entries=entries, total=200)
        parser, _ = build_parser()
        args = parser.parse_args(["ls", "/"])

        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
                LsCommand().execute(args)

        self.assertIn("Warning", mock_err.getvalue())
        self.assertIn("200", mock_err.getvalue())

    @patch.object(LsCommand, "_create_client")
    def test_ls_no_warning_when_pagination_explicit(self, mock_create):
        entries = [_make_dir(), _make_file()]
        mock_create.return_value = self._make_client_mock(entries=entries, total=200)
        parser, _ = build_parser()
        args = parser.parse_args(["ls", "--limit", "10", "/"])

        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
                LsCommand().execute(args)

        self.assertNotIn("Warning", mock_err.getvalue())


class TestCpCommand(unittest.TestCase):
    @patch.object(CpCommand, "_create_client")
    def test_single_copy(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["cp", "/src/file.txt", "/dst"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            CpCommand().execute(args)

        mock_client.file.copy.assert_called_once_with("/src/file.txt", "/dst")
        self.assertIn("Copied", mock_out.getvalue())

    @patch.object(CpCommand, "_create_client")
    def test_batch_copy(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["cp", "/a", "/b", "/dst"])

        with patch("sys.stdout", new_callable=io.StringIO):
            CpCommand().execute(args)

        mock_client.file.batch_copy.assert_called_once_with("/a", "/b", dest_dir="/dst")


class TestMvCommand(unittest.TestCase):
    @patch.object(MvCommand, "_create_client")
    def test_single_move(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["mv", "/src/file.txt", "/dst"])

        with patch("sys.stdout", new_callable=io.StringIO):
            MvCommand().execute(args)

        mock_client.file.move.assert_called_once_with("/src/file.txt", "/dst")

    @patch.object(MvCommand, "_create_client")
    def test_batch_move(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["mv", "/a", "/b", "/dst"])

        with patch("sys.stdout", new_callable=io.StringIO):
            MvCommand().execute(args)

        mock_client.file.batch_move.assert_called_once_with("/a", "/b", dest_dir="/dst")


class TestRmCommand(unittest.TestCase):
    @patch.object(RmCommand, "_create_client")
    def test_single_delete(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["rm", "/file.txt"])

        with patch("sys.stdout", new_callable=io.StringIO):
            RmCommand().execute(args)

        mock_client.file.delete.assert_called_once_with("/file.txt", recursive=False)

    @patch.object(RmCommand, "_create_client")
    def test_recursive_delete(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["rm", "-r", "/dir"])

        with patch("sys.stdout", new_callable=io.StringIO):
            RmCommand().execute(args)

        mock_client.file.delete.assert_called_once_with("/dir", recursive=True)

    @patch.object(RmCommand, "_create_client")
    def test_batch_delete(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["rm", "/a", "/b"])

        with patch("sys.stdout", new_callable=io.StringIO):
            RmCommand().execute(args)

        mock_client.file.batch_delete.assert_called_once_with(
            "/a", "/b", recursive=False
        )


class TestMkdirCommand(unittest.TestCase):
    @patch.object(MkdirCommand, "_create_client")
    def test_mkdir(self, mock_create):
        mock_client = MagicMock()
        mock_client.file.create_directory.return_value = _make_dir(
            name="newdir", id="999"
        )
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["mkdir", "/newdir"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            MkdirCommand().execute(args)

        mock_client.file.create_directory.assert_called_once_with(
            "/newdir", parents=False
        )
        self.assertIn("999", mock_out.getvalue())

    @patch.object(MkdirCommand, "_create_client")
    def test_mkdir_parents(self, mock_create):
        mock_client = MagicMock()
        mock_client.file.create_directory.return_value = _make_dir()
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["mkdir", "-p", "/a/b/c"])

        with patch("sys.stdout", new_callable=io.StringIO):
            MkdirCommand().execute(args)

        mock_client.file.create_directory.assert_called_once_with(
            "/a/b/c", parents=True
        )


class TestUploadCommand(unittest.TestCase):
    @patch.object(UploadCommand, "_create_client")
    def test_upload(self, mock_create):
        mock_client = MagicMock()
        mock_client.file.stat.side_effect = NotFoundError("Not found")
        mock_client.file.upload.return_value = _make_file(name="uploaded.txt")
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["upload", "/local/file.txt", "/remote/file.txt"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            UploadCommand().execute(args)

        mock_client.file.upload.assert_called_once_with(
            "/remote/file.txt", "/local/file.txt", instant_only=False
        )
        output = mock_out.getvalue()
        self.assertIn("abc123", output)
        self.assertIn("1024", output)

    @patch.object(UploadCommand, "_create_client")
    def test_upload_to_directory(self, mock_create):
        mock_client = MagicMock()
        # remote path resolves to a directory
        mock_client.file.stat.return_value = _make_dir(name="remotedir", id="300")
        mock_client.file.upload.return_value = _make_file(name="uploaded.txt")
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["upload", "/local/path/file.txt", "/remote/dir"])

        with patch("sys.stdout", new_callable=io.StringIO):
            UploadCommand().execute(args)

        mock_client.file.upload.assert_called_once_with(
            "/remote/dir/file.txt", "/local/path/file.txt", instant_only=False
        )


class TestStatCommand(unittest.TestCase):
    @patch.object(StatCommand, "_create_client")
    def test_stat_file(self, mock_create):
        mock_client = MagicMock()
        mock_client.file.stat.return_value = _make_file()
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["stat", "/test.txt"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            StatCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("test.txt", output)
        self.assertIn("File", output)
        self.assertIn("abc123", output)
        self.assertIn("1024", output)

    @patch.object(StatCommand, "_create_client")
    def test_stat_directory(self, mock_create):
        mock_client = MagicMock()
        mock_client.file.stat.return_value = _make_dir()
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["stat", "/testdir"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            StatCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("testdir", output)
        self.assertIn("Directory", output)
        self.assertIn("5", output)


class TestMainEntryPoint(unittest.TestCase):
    @patch.object(LsCommand, "_create_client")
    def test_main_dispatches_to_command(self, mock_create):
        mock_client = MagicMock()
        mock_client.file.list.return_value = _make_lazy([])
        mock_create.return_value = mock_client

        with patch("sys.stdout", new_callable=io.StringIO):
            main(["ls", "/"])

        mock_client.file.list.assert_called_once()


def _make_task(
    info_hash="abc123hash",
    name="test-download.png",
    size=2048,
    status=TaskStatus.DOWNLOADING,
    percent_done=50.0,
):
    return CloudTask(
        info_hash=info_hash,
        name=name,
        size=size,
        status=status,
        percent_done=percent_done,
        url="https://example.com/file.png",
        file_id="",
        pick_code="",
        folder_id="0",
        add_time=datetime(2025, 1, 1),
    )


class TestIdCommand(unittest.TestCase):
    @patch.object(IdCommand, "_create_client")
    def test_id_file(self, mock_create):
        mock_client = MagicMock()
        mock_client.file.id.return_value = _make_file()
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["id", "200"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            IdCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("test.txt", output)
        self.assertIn("File", output)
        self.assertIn("abc123", output)
        self.assertIn("1024", output)

    @patch.object(IdCommand, "_create_client")
    def test_id_directory(self, mock_create):
        mock_client = MagicMock()
        mock_client.file.id.return_value = _make_dir()
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["id", "100"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            IdCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("testdir", output)
        self.assertIn("Directory", output)
        self.assertIn("5", output)


class TestDownloadCommand(unittest.TestCase):
    @patch.object(DownloadQuotaCommand, "_create_client")
    def test_download_quota(self, mock_create):
        mock_client = MagicMock()
        mock_client.download.quota.return_value = DownloadQuota(quota=2985, total=3000)
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["download", "quota"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            DownloadCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("2985", output)
        self.assertIn("3000", output)

    @patch.object(DownloadListCommand, "_create_client")
    def test_download_list(self, mock_create):
        mock_client = MagicMock()
        mock_client.download.list.return_value = _make_lazy([_make_task()])
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["download", "list"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            DownloadCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("abc123hash", output)
        self.assertIn("test-download.png", output)

    @patch.object(DownloadListCommand, "_create_client")
    def test_download_list_json(self, mock_create):
        mock_client = MagicMock()
        mock_client.download.list.return_value = _make_lazy([_make_task()])
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["download", "list", "--format", "json"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            DownloadCommand().execute(args)

        data = json.loads(mock_out.getvalue())
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["Hash"], "abc123hash")
        self.assertEqual(data[0]["Name"], "test-download.png")

    @patch.object(DownloadListCommand, "_create_client")
    def test_download_list_table(self, mock_create):
        mock_client = MagicMock()
        mock_client.download.list.return_value = _make_lazy([_make_task()])
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["download", "list", "--format", "table"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            DownloadCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("Hash", output)
        self.assertIn("Name", output)
        self.assertIn("abc123hash", output)

    @patch.object(DownloadListCommand, "_create_client")
    def test_download_list_offset(self, mock_create):
        mock_client = MagicMock()
        mock_client.download.list.return_value = _make_lazy([], total=0)
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(
            ["download", "list", "--offset", "30", "--limit", "30"]
        )

        with patch("sys.stdout", new_callable=io.StringIO):
            DownloadCommand().execute(args)

        mock_client.download.list.assert_called_once()

    @patch.object(DownloadAddCommand, "_create_client")
    def test_download_add_single(self, mock_create):
        mock_client = MagicMock()
        mock_client.download.add_url.return_value = _make_task()
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["download", "add", "https://example.com/file.png"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            DownloadCommand().execute(args)

        mock_client.download.add_url.assert_called_once_with(
            "https://example.com/file.png", dest_dir=None
        )
        output = mock_out.getvalue()
        self.assertIn("abc123hash", output)

    @patch.object(DownloadAddCommand, "_create_client")
    def test_download_add_single_with_dest(self, mock_create):
        mock_client = MagicMock()
        mock_client.download.add_url.return_value = _make_task()
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(
            ["download", "add", "--dest", "/my/folder", "https://example.com/file.png"]
        )

        with patch("sys.stdout", new_callable=io.StringIO):
            DownloadCommand().execute(args)

        mock_client.download.add_url.assert_called_once_with(
            "https://example.com/file.png", dest_dir="/my/folder"
        )

    @patch.object(DownloadAddCommand, "_create_client")
    def test_download_add_multiple(self, mock_create):
        mock_client = MagicMock()
        mock_client.download.add_urls.return_value = [
            _make_task(info_hash="hash1"),
            _make_task(info_hash="hash2"),
        ]
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(
            [
                "download",
                "add",
                "https://example.com/a.png",
                "https://example.com/b.png",
            ]
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            DownloadCommand().execute(args)

        mock_client.download.add_urls.assert_called_once_with(
            "https://example.com/a.png",
            "https://example.com/b.png",
            dest_dir=None,
        )
        output = mock_out.getvalue()
        self.assertIn("hash1", output)
        self.assertIn("hash2", output)

    @patch.object(DownloadDeleteCommand, "_create_client")
    def test_download_delete(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["download", "delete", "hash1", "hash2"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            DownloadCommand().execute(args)

        mock_client.download.delete.assert_called_once_with("hash1", "hash2")
        output = mock_out.getvalue()
        self.assertIn("hash1", output)
        self.assertIn("hash2", output)


class TestBuildParser(unittest.TestCase):
    def test_all_commands_registered(self):
        _, commands = build_parser()
        expected = [
            "auth",
            "config",
            "cp",
            "download",
            "find",
            "id",
            "login",
            "logout",
            "ls",
            "mkdir",
            "mv",
            "rm",
            "stat",
            "upload",
            "url",
        ]
        for cmd in expected:
            self.assertIn(cmd, commands)


class TestFindCommand(unittest.TestCase):
    def _make_client_mock(self, entries=None, total=None):
        if entries is None:
            entries = [_make_dir(), _make_file()]
        mock_client = MagicMock()
        mock_client.file.find.return_value = _make_lazy(entries, total=total)
        return mock_client

    @patch.object(FindCommand, "_create_client")
    def test_find_table_format(self, mock_create):
        mock_create.return_value = self._make_client_mock()
        parser, _ = build_parser()
        args = parser.parse_args(["find", "test"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            FindCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("testdir/", output)
        self.assertIn("test.txt", output)

    @patch.object(FindCommand, "_create_client")
    def test_find_global_search(self, mock_create):
        mock_create.return_value = self._make_client_mock()
        parser, _ = build_parser()
        args = parser.parse_args(["find", "keyword"])

        with patch("sys.stdout", new_callable=io.StringIO):
            FindCommand().execute(args)

        call_kwargs = mock_create.return_value.file.find.call_args
        self.assertIsNone(call_kwargs.kwargs["path"])
        self.assertEqual(call_kwargs.args[0], "keyword")

    @patch.object(FindCommand, "_create_client")
    def test_find_with_path(self, mock_create):
        mock_create.return_value = self._make_client_mock()
        parser, _ = build_parser()
        args = parser.parse_args(["find", "/docs", "keyword"])

        with patch("sys.stdout", new_callable=io.StringIO):
            FindCommand().execute(args)

        call_kwargs = mock_create.return_value.file.find.call_args
        self.assertEqual(call_kwargs.kwargs["path"], "/docs")
        self.assertEqual(call_kwargs.args[0], "keyword")

    @patch.object(FindCommand, "_create_client")
    def test_find_pagination_args(self, mock_create):
        entries = [_make_file(name=f"f{i}.txt", id=str(i)) for i in range(20)]
        mock_create.return_value = self._make_client_mock(entries=entries)
        parser, _ = build_parser()
        args = parser.parse_args(["find", "--offset", "5", "--limit", "5", "test"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            FindCommand().execute(args)

        # Should show items 5..9
        output = mock_out.getvalue()
        self.assertIn("f5.txt", output)
        self.assertIn("f9.txt", output)
        self.assertNotIn("f4.txt", output)
        self.assertNotIn("f10.txt", output)

    @patch.object(FindCommand, "_create_client")
    def test_find_plain_format(self, mock_create):
        mock_create.return_value = self._make_client_mock(
            entries=[_make_file(name="note.txt", id="888")],
        )
        parser, _ = build_parser()
        args = parser.parse_args(["find", "--format", "plain", "note"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            FindCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("note.txt", output)
        self.assertIn("888", output)

    @patch.object(FindCommand, "_create_client")
    def test_find_empty_results(self, mock_create):
        mock_create.return_value = self._make_client_mock(entries=[])
        parser, _ = build_parser()
        args = parser.parse_args(["find", "--format", "plain", "nonexistent"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            FindCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("No entries found.", output)

    @patch.object(FindCommand, "_create_client")
    def test_find_pagination_warning(self, mock_create):
        entries = [_make_file(name=f"f{i}.txt", id=str(i)) for i in range(10)]
        mock_create.return_value = self._make_client_mock(
            entries=entries, total=DEFAULT_PAGE_SIZE + 1
        )
        parser, _ = build_parser()
        args = parser.parse_args(["find", "f"])

        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
                FindCommand().execute(args)

        self.assertIn("Warning", mock_err.getvalue())


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


class TestUrlCommand(unittest.TestCase):
    @patch.object(UrlCommand, "_create_client")
    def test_plain_format(self, mock_create):
        mock_client = MagicMock()
        mock_client.file.url.return_value = _make_url()
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["url", "/test.bin"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            UrlCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("https://cdn.115.com/test.bin?t=123", output)
        self.assertIn("test.bin", output)
        self.assertIn("4096", output)
        self.assertIn("Mozilla/5.0", output)
        self.assertIn("UID=u1", output)

    @patch.object(UrlCommand, "_create_client")
    def test_aria2c_format(self, mock_create):
        cfg = ConfigParser()
        cfg["download"] = {
            "min_split_size": "2M",
            "max_connection": "10",
        }
        mock_client = MagicMock()
        mock_client.file.url.return_value = _make_url()
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["url", "--format", "aria2c", "/test.bin"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            UrlCommand(config=cfg).execute(args)

        output = mock_out.getvalue()
        self.assertIn("aria2c", output)
        self.assertIn("-o", output)
        self.assertIn("test.bin", output)
        self.assertIn("-k2M", output)
        self.assertIn("-x10", output)
        self.assertIn("-s10", output)
        self.assertNotIn("--checksum", output)
        self.assertIn("User-Agent: Mozilla/5.0", output)
        self.assertIn("Referer: https://115.com", output)
        self.assertIn("UID=u1", output)
        self.assertIn("https://cdn.115.com/test.bin?t=123", output)

    @patch.object(UrlCommand, "_create_client")
    def test_aria2c_format_with_check_integrity(self, mock_create):
        cfg = ConfigParser()
        cfg["download"] = {
            "min_split_size": "2M",
            "max_connection": "10",
        }
        mock_client = MagicMock()
        mock_client.file.url.return_value = _make_url()
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(
            ["url", "--format", "aria2c", "--check-integrity", "/test.bin"]
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            UrlCommand(config=cfg).execute(args)

        output = mock_out.getvalue()
        self.assertIn(f"--checksum=sha-1={_make_url().sha1}", output)


class TestFetchCommand(unittest.TestCase):
    def _make_mock_client(self, file=None):
        if file is None:
            file = _make_file(name="remote.bin", size=1024)
        mock_client = MagicMock()
        mock_client.file.stat.return_value = file
        return mock_client

    @patch.object(FetchCommand, "_create_client")
    def test_fetch_saves_file(self, mock_create):
        mock_client = self._make_mock_client()
        mock_create.return_value = mock_client
        chunk = b"x" * 1024
        mock_remote = MagicMock()
        mock_remote.__enter__ = lambda s: s
        mock_remote.__exit__ = MagicMock(return_value=False)
        mock_remote.read.side_effect = [chunk, b""]
        mock_client.file.open.return_value = mock_remote

        parser, _ = build_parser()
        args = parser.parse_args(["fetch", "/remote/remote.bin"])

        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                    FetchCommand().execute(args)
                self.assertTrue(os.path.exists("remote.bin"))
                self.assertIn("remote.bin", mock_out.getvalue())
            finally:
                os.chdir(orig_dir)

    @patch.object(FetchCommand, "_create_client")
    def test_fetch_custom_output_path(self, mock_create):
        mock_client = self._make_mock_client()
        mock_create.return_value = mock_client
        mock_remote = MagicMock()
        mock_remote.__enter__ = lambda s: s
        mock_remote.__exit__ = MagicMock(return_value=False)
        mock_remote.read.side_effect = [b"x" * 1024, b""]
        mock_client.file.open.return_value = mock_remote

        parser, _ = build_parser()

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "custom.bin")
            args = parser.parse_args(["fetch", "/remote/remote.bin", "-o", out_path])
            with patch("sys.stdout", new_callable=io.StringIO):
                FetchCommand().execute(args)
            self.assertTrue(os.path.exists(out_path))

    @patch.object(FetchCommand, "_create_client")
    def test_fetch_custom_chunk_size(self, mock_create):
        mock_client = self._make_mock_client()
        mock_create.return_value = mock_client
        parser, _ = build_parser()
        args = parser.parse_args(["fetch", "/remote/remote.bin", "--chunk-size", "4MB"])
        self.assertEqual(args.chunk_size, 4 * 1024 * 1024)

    @patch.object(FetchCommand, "_create_client")
    def test_fetch_output_to_directory_uses_remote_name(self, mock_create):
        mock_client = self._make_mock_client()
        mock_create.return_value = mock_client
        mock_remote = MagicMock()
        mock_remote.__enter__ = lambda s: s
        mock_remote.__exit__ = MagicMock(return_value=False)
        mock_remote.read.side_effect = [b"x" * 1024, b""]
        mock_client.file.open.return_value = mock_remote

        with tempfile.TemporaryDirectory() as tmpdir:
            parser, _ = build_parser()
            args = parser.parse_args(["fetch", "/remote/remote.bin", "-o", tmpdir])
            with patch("sys.stdout", new_callable=io.StringIO):
                FetchCommand().execute(args)
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "remote.bin")))

    @patch("cli115.cmds.fetch.sha1_file")
    @patch.object(FetchCommand, "_create_client")
    def test_fetch_check_integrity_passes(self, mock_create, mock_sha1):
        file = _make_file(name="remote.bin", size=1024)
        mock_client = self._make_mock_client(file=file)
        mock_create.return_value = mock_client
        mock_sha1.return_value = (file.sha1, file.size)
        mock_remote = MagicMock()
        mock_remote.__enter__ = lambda s: s
        mock_remote.__exit__ = MagicMock(return_value=False)
        mock_remote.read.side_effect = [b"x" * 1024, b""]
        mock_client.file.open.return_value = mock_remote

        parser, _ = build_parser()
        args = parser.parse_args(["fetch", "/remote/remote.bin", "--check-integrity"])

        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                    FetchCommand().execute(args)
                self.assertIn("Checking file integrity", mock_out.getvalue())
            finally:
                os.chdir(orig_dir)

    @patch("cli115.cmds.fetch.sha1_file")
    @patch.object(FetchCommand, "_create_client")
    def test_fetch_check_integrity_size_mismatch_raises(self, mock_create, mock_sha1):
        file = _make_file(name="remote.bin", size=1024)
        mock_client = self._make_mock_client(file=file)
        mock_create.return_value = mock_client
        mock_sha1.return_value = (file.sha1, 512)
        mock_remote = MagicMock()
        mock_remote.__enter__ = lambda s: s
        mock_remote.__exit__ = MagicMock(return_value=False)
        mock_remote.read.side_effect = [b"x" * 1024, b""]
        mock_client.file.open.return_value = mock_remote

        parser, _ = build_parser()
        args = parser.parse_args(["fetch", "/remote/remote.bin", "--check-integrity"])

        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = os.getcwd()
            os.chdir(tmpdir)
            try:
                with self.assertRaises(ValueError) as ctx:
                    with patch("sys.stdout", new_callable=io.StringIO):
                        FetchCommand().execute(args)
                self.assertIn("Size mismatch", str(ctx.exception))
            finally:
                os.chdir(orig_dir)

    @patch("cli115.cmds.fetch.sha1_file")
    @patch.object(FetchCommand, "_create_client")
    def test_fetch_check_integrity_sha1_mismatch_raises(self, mock_create, mock_sha1):
        file = _make_file(name="remote.bin", size=1024)
        mock_client = self._make_mock_client(file=file)
        mock_create.return_value = mock_client
        mock_sha1.return_value = ("wrong_sha1", file.size)
        mock_remote = MagicMock()
        mock_remote.__enter__ = lambda s: s
        mock_remote.__exit__ = MagicMock(return_value=False)
        mock_remote.read.side_effect = [b"x" * 1024, b""]
        mock_client.file.open.return_value = mock_remote

        parser, _ = build_parser()
        args = parser.parse_args(["fetch", "/remote/remote.bin", "--check-integrity"])

        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = os.getcwd()
            os.chdir(tmpdir)
            try:
                with self.assertRaises(ValueError) as ctx:
                    with patch("sys.stdout", new_callable=io.StringIO):
                        FetchCommand().execute(args)
                self.assertIn("SHA1 mismatch", str(ctx.exception))
            finally:
                os.chdir(orig_dir)


if __name__ == "__main__":
    unittest.main()
