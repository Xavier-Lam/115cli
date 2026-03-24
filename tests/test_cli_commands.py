import io
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

import configparser

from cli115.cmds.auth import AuthCommand, _parse_cookie_string
from cli115.cmds.config_cmd import ConfigCommand
from cli115.cmds.cp import CpCommand
from cli115.cmds.download import (
    DownloadAddCommand,
    DownloadCommand,
    DownloadDeleteCommand,
    DownloadListCommand,
    DownloadQuotaCommand,
)
from cli115.cmds.download_info import DownloadInfoCommand
from cli115.cmds.id import IdCommand
from cli115.cmds.info import InfoCommand
from cli115.cmds.find import FindCommand
from cli115.cmds.ls import LsCommand
from cli115.cmds.mkdir import MkdirCommand
from cli115.cmds.mv import MvCommand
from cli115.cmds.rm import RmCommand
from cli115.cmds.upload import UploadCommand
from cli115.cli import build_parser, main
from cli115.client.base import (
    CloudTask,
    Directory,
    DownloadInfo,
    DownloadQuota,
    File,
    Pagination,
    TaskStatus,
)


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


class TestParseCookieString(unittest.TestCase):
    def test_parses_standard_cookie(self):
        cookie = "UID=u1; CID=c1; SEID=s1; KID=k1"
        result = _parse_cookie_string(cookie)
        self.assertEqual(result["UID"], "u1")
        self.assertEqual(result["CID"], "c1")
        self.assertEqual(result["SEID"], "s1")
        self.assertEqual(result["KID"], "k1")

    def test_parses_cookie_with_extra_values(self):
        cookie = "UID=u1; CID=c1; SEID=s1; KID=k1; OTHER=x"
        result = _parse_cookie_string(cookie)
        self.assertEqual(len(result), 5)
        self.assertEqual(result["OTHER"], "x")


class TestAuthCookieCommand(unittest.TestCase):
    @patch("cli115.cmds.auth.save_cookie_credential")
    def test_saves_credential(self, mock_save):
        from pathlib import Path

        mock_save.return_value = Path("/tmp/cookie_u1.json")
        parser = build_parser()
        args = parser.parse_args(
            ["auth", "cookie", "u1", "UID=u1; CID=c1; SEID=s1; KID=k1"]
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            COMMANDS = {"auth": AuthCommand()}
            COMMANDS["auth"].execute(args)

        mock_save.assert_called_once()
        call_args = mock_save.call_args
        self.assertEqual(call_args[0][0], "u1")
        self.assertIn("UID", call_args[0][1])

    @patch("cli115.cmds.auth.save_cookie_credential")
    def test_missing_cookies_exits(self, mock_save):
        parser = build_parser()
        args = parser.parse_args(["auth", "cookie", "u1", "UID=u1; CID=c1"])

        with self.assertRaises(SystemExit) as ctx:
            with patch("sys.stderr", new_callable=io.StringIO):
                COMMANDS = {"auth": AuthCommand()}
                COMMANDS["auth"].execute(args)

        self.assertEqual(ctx.exception.code, 1)
        mock_save.assert_not_called()


class TestLsCommand(unittest.TestCase):
    def _make_client_mock(self, entries=None, pagination=None):
        if entries is None:
            entries = [_make_dir(), _make_file()]
        if pagination is None:
            pagination = Pagination(total=2, offset=0, limit=115)
        mock_client = MagicMock()
        mock_client.file.list.return_value = (entries, pagination)
        return mock_client

    @patch.object(LsCommand, "_create_client")
    def test_ls_short(self, mock_create):
        mock_create.return_value = self._make_client_mock()
        parser = build_parser()
        args = parser.parse_args(["ls", "/"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            LsCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("testdir/", output)
        self.assertIn("test.txt", output)

    @patch.object(LsCommand, "_create_client")
    def test_ls_long(self, mock_create):
        mock_create.return_value = self._make_client_mock()
        parser = build_parser()
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
        parser = build_parser()
        args = parser.parse_args(["ls", "--offset", "20", "--limit", "10", "/"])

        with patch("sys.stdout", new_callable=io.StringIO):
            LsCommand().execute(args)

        call_kwargs = mock_create.return_value.file.list.call_args.kwargs
        self.assertEqual(call_kwargs["limit"], 10)
        self.assertEqual(call_kwargs["offset"], 20)

    @patch.object(LsCommand, "_create_client")
    def test_ls_sort_options(self, mock_create):
        mock_create.return_value = self._make_client_mock()
        parser = build_parser()
        args = parser.parse_args(["ls", "--sort", "size", "--desc", "/"])

        with patch("sys.stdout", new_callable=io.StringIO):
            LsCommand().execute(args)

        from cli115.client.base import SortField, SortOrder

        call_kwargs = mock_create.return_value.file.list.call_args.kwargs
        self.assertEqual(call_kwargs["sort"], SortField.SIZE)

    @patch.object(LsCommand, "_create_client")
    def test_ls_sort_created(self, mock_create):
        from cli115.client.base import SortField

        mock_create.return_value = self._make_client_mock()
        parser = build_parser()
        args = parser.parse_args(["ls", "--sort", "created", "/"])

        with patch("sys.stdout", new_callable=io.StringIO):
            LsCommand().execute(args)

        call_kwargs = mock_create.return_value.file.list.call_args.kwargs
        self.assertEqual(call_kwargs["sort"], SortField.CREATED_TIME)

    @patch.object(LsCommand, "_create_client")
    def test_ls_sort_opened(self, mock_create):
        from cli115.client.base import SortField

        mock_create.return_value = self._make_client_mock()
        parser = build_parser()
        args = parser.parse_args(["ls", "--sort", "opened", "/"])

        with patch("sys.stdout", new_callable=io.StringIO):
            LsCommand().execute(args)

        call_kwargs = mock_create.return_value.file.list.call_args.kwargs
        self.assertEqual(call_kwargs["sort"], SortField.OPEN_TIME)

    @patch.object(LsCommand, "_create_client")
    def test_ls_warning_when_total_exceeds_default(self, mock_create):
        pagination = Pagination(total=200, offset=0, limit=115)
        mock_create.return_value = self._make_client_mock(pagination=pagination)
        parser = build_parser()
        args = parser.parse_args(["ls", "/"])

        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
                LsCommand().execute(args)

        self.assertIn("Warning", mock_err.getvalue())
        self.assertIn("200", mock_err.getvalue())

    @patch.object(LsCommand, "_create_client")
    def test_ls_no_warning_when_pagination_explicit(self, mock_create):
        pagination = Pagination(total=200, offset=0, limit=10)
        mock_create.return_value = self._make_client_mock(pagination=pagination)
        parser = build_parser()
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
        parser = build_parser()
        args = parser.parse_args(["cp", "/src/file.txt", "/dst"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            CpCommand().execute(args)

        mock_client.file.copy.assert_called_once_with("/src/file.txt", "/dst")
        self.assertIn("Copied", mock_out.getvalue())

    @patch.object(CpCommand, "_create_client")
    def test_batch_copy(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        parser = build_parser()
        args = parser.parse_args(["cp", "/a", "/b", "/dst"])

        with patch("sys.stdout", new_callable=io.StringIO):
            CpCommand().execute(args)

        mock_client.file.batch_copy.assert_called_once_with("/a", "/b", dest_dir="/dst")


class TestMvCommand(unittest.TestCase):
    @patch.object(MvCommand, "_create_client")
    def test_single_move(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        parser = build_parser()
        args = parser.parse_args(["mv", "/src/file.txt", "/dst"])

        with patch("sys.stdout", new_callable=io.StringIO):
            MvCommand().execute(args)

        mock_client.file.move.assert_called_once_with("/src/file.txt", "/dst")

    @patch.object(MvCommand, "_create_client")
    def test_batch_move(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        parser = build_parser()
        args = parser.parse_args(["mv", "/a", "/b", "/dst"])

        with patch("sys.stdout", new_callable=io.StringIO):
            MvCommand().execute(args)

        mock_client.file.batch_move.assert_called_once_with("/a", "/b", dest_dir="/dst")


class TestRmCommand(unittest.TestCase):
    @patch.object(RmCommand, "_create_client")
    def test_single_delete(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        parser = build_parser()
        args = parser.parse_args(["rm", "/file.txt"])

        with patch("sys.stdout", new_callable=io.StringIO):
            RmCommand().execute(args)

        mock_client.file.delete.assert_called_once_with("/file.txt", recursive=False)

    @patch.object(RmCommand, "_create_client")
    def test_recursive_delete(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        parser = build_parser()
        args = parser.parse_args(["rm", "-r", "/dir"])

        with patch("sys.stdout", new_callable=io.StringIO):
            RmCommand().execute(args)

        mock_client.file.delete.assert_called_once_with("/dir", recursive=True)

    @patch.object(RmCommand, "_create_client")
    def test_batch_delete(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        parser = build_parser()
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
        parser = build_parser()
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
        parser = build_parser()
        args = parser.parse_args(["mkdir", "-p", "/a/b/c"])

        with patch("sys.stdout", new_callable=io.StringIO):
            MkdirCommand().execute(args)

        mock_client.file.create_directory.assert_called_once_with(
            "/a/b/c", parents=True
        )

    @patch.object(MkdirCommand, "_create_client")
    def test_mkdir_json_format(self, mock_create):
        import json

        mock_client = MagicMock()
        mock_client.file.create_directory.return_value = _make_dir(
            name="newdir", id="999"
        )
        mock_create.return_value = mock_client
        parser = build_parser()
        args = parser.parse_args(["mkdir", "--format", "json", "/newdir"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            MkdirCommand().execute(args)

        data = json.loads(mock_out.getvalue())
        self.assertEqual(data["ID"], "999")
        self.assertEqual(data["Name"], "newdir")


class TestUploadCommand(unittest.TestCase):
    @patch.object(UploadCommand, "_create_client")
    def test_upload(self, mock_create):
        mock_client = MagicMock()
        mock_client.file.upload.return_value = _make_file(name="uploaded.txt")
        mock_create.return_value = mock_client
        parser = build_parser()
        args = parser.parse_args(["upload", "/local/file.txt", "/remote/file.txt"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            UploadCommand().execute(args)

        mock_client.file.upload.assert_called_once_with(
            "/remote/file.txt", "/local/file.txt"
        )
        output = mock_out.getvalue()
        self.assertIn("abc123", output)
        self.assertIn("1024", output)


class TestInfoCommand(unittest.TestCase):
    @patch.object(InfoCommand, "_create_client")
    def test_info_file(self, mock_create):
        mock_client = MagicMock()
        mock_client.file.info.return_value = _make_file()
        mock_create.return_value = mock_client
        parser = build_parser()
        args = parser.parse_args(["info", "/test.txt"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            InfoCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("test.txt", output)
        self.assertIn("File", output)
        self.assertIn("abc123", output)
        self.assertIn("1024", output)

    @patch.object(InfoCommand, "_create_client")
    def test_info_directory(self, mock_create):
        mock_client = MagicMock()
        mock_client.file.info.return_value = _make_dir()
        mock_create.return_value = mock_client
        parser = build_parser()
        args = parser.parse_args(["info", "/testdir"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            InfoCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("testdir", output)
        self.assertIn("Directory", output)
        self.assertIn("5", output)

    @patch.object(InfoCommand, "_create_client")
    def test_info_json_format(self, mock_create):
        import json

        mock_client = MagicMock()
        mock_client.file.info.return_value = _make_file()
        mock_create.return_value = mock_client
        parser = build_parser()
        args = parser.parse_args(["info", "--format", "json", "/test.txt"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            InfoCommand().execute(args)

        data = json.loads(mock_out.getvalue())
        self.assertEqual(data["Name"], "test.txt")
        self.assertEqual(data["SHA1"], "abc123")


class TestMainEntryPoint(unittest.TestCase):
    @patch.object(LsCommand, "_create_client")
    def test_main_dispatches_to_command(self, mock_create):
        mock_client = MagicMock()
        mock_client.file.list.return_value = (
            [],
            Pagination(total=0, offset=0, limit=115),
        )
        mock_create.return_value = mock_client

        with patch("sys.stdout", new_callable=io.StringIO):
            main(["ls", "/"])

        mock_client.file.list.assert_called_once()

    def test_main_no_args_exits(self):
        with self.assertRaises(SystemExit):
            main([])


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
        parser = build_parser()
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
        parser = build_parser()
        args = parser.parse_args(["id", "100"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            IdCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("testdir", output)
        self.assertIn("Directory", output)
        self.assertIn("5", output)

    @patch.object(IdCommand, "_create_client")
    def test_id_json_format(self, mock_create):
        import json

        mock_client = MagicMock()
        mock_client.file.id.return_value = _make_file()
        mock_create.return_value = mock_client
        parser = build_parser()
        args = parser.parse_args(["id", "--format", "json", "200"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            IdCommand().execute(args)

        data = json.loads(mock_out.getvalue())
        self.assertEqual(data["Name"], "test.txt")
        self.assertEqual(data["SHA1"], "abc123")


class TestDownloadCommand(unittest.TestCase):
    @patch.object(DownloadQuotaCommand, "_create_client")
    def test_download_quota(self, mock_create):
        mock_client = MagicMock()
        mock_client.download.quota.return_value = DownloadQuota(quota=2985, total=3000)
        mock_create.return_value = mock_client
        parser = build_parser()
        args = parser.parse_args(["download", "quota"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            DownloadCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("2985", output)
        self.assertIn("3000", output)

    @patch.object(DownloadListCommand, "_create_client")
    def test_download_list(self, mock_create):
        mock_client = MagicMock()
        mock_client.download.list.return_value = (
            [_make_task()],
            Pagination(total=1, offset=0, limit=30),
        )
        mock_create.return_value = mock_client
        parser = build_parser()
        args = parser.parse_args(["download", "list"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            DownloadCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("abc123hash", output)
        self.assertIn("test-download.png", output)

    @patch.object(DownloadListCommand, "_create_client")
    def test_download_list_json(self, mock_create):
        import json as _json

        mock_client = MagicMock()
        mock_client.download.list.return_value = (
            [_make_task()],
            Pagination(total=1, offset=0, limit=30),
        )
        mock_create.return_value = mock_client
        parser = build_parser()
        args = parser.parse_args(["download", "list", "--format", "json"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            DownloadCommand().execute(args)

        data = _json.loads(mock_out.getvalue())
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["Hash"], "abc123hash")
        self.assertEqual(data[0]["Name"], "test-download.png")

    @patch.object(DownloadListCommand, "_create_client")
    def test_download_list_table(self, mock_create):
        mock_client = MagicMock()
        mock_client.download.list.return_value = (
            [_make_task()],
            Pagination(total=1, offset=0, limit=30),
        )
        mock_create.return_value = mock_client
        parser = build_parser()
        args = parser.parse_args(["download", "list", "--format", "table"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            DownloadCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("Hash", output)
        self.assertIn("Name", output)
        self.assertIn("abc123hash", output)

    @patch.object(DownloadListCommand, "_create_client")
    def test_download_list_page(self, mock_create):
        mock_client = MagicMock()
        mock_client.download.list.return_value = (
            [],
            Pagination(total=0, offset=0, limit=30),
        )
        mock_create.return_value = mock_client
        parser = build_parser()
        args = parser.parse_args(["download", "list", "--page", "2"])

        with patch("sys.stdout", new_callable=io.StringIO):
            DownloadCommand().execute(args)

        mock_client.download.list.assert_called_once_with(2)

    @patch.object(DownloadAddCommand, "_create_client")
    def test_download_add_single(self, mock_create):
        mock_client = MagicMock()
        mock_client.download.add_url.return_value = _make_task()
        mock_create.return_value = mock_client
        parser = build_parser()
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
        parser = build_parser()
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
        parser = build_parser()
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
        parser = build_parser()
        args = parser.parse_args(["download", "delete", "hash1", "hash2"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            DownloadCommand().execute(args)

        mock_client.download.delete.assert_called_once_with("hash1", "hash2")
        output = mock_out.getvalue()
        self.assertIn("hash1", output)
        self.assertIn("hash2", output)

    @patch.object(DownloadQuotaCommand, "_create_client")
    def test_download_quota_json(self, mock_create):
        import json

        mock_client = MagicMock()
        mock_client.download.quota.return_value = DownloadQuota(quota=100, total=3000)
        mock_create.return_value = mock_client
        parser = build_parser()
        args = parser.parse_args(["download", "quota", "--format", "json"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            DownloadCommand().execute(args)

        data = json.loads(mock_out.getvalue())
        self.assertEqual(data["Remaining"], 100)
        self.assertEqual(data["Total"], 3000)


class TestBuildParser(unittest.TestCase):
    def test_all_commands_registered(self):
        parser = build_parser()
        expected = [
            "auth",
            "config",
            "ls",
            "find",
            "cp",
            "mv",
            "rm",
            "mkdir",
            "upload",
            "info",
            "id",
            "download",
            "download-info",
        ]
        for cmd in expected:
            self.assertIn(cmd, parser._subparsers._group_actions[0].choices)


class TestFindCommand(unittest.TestCase):
    def _make_client_mock(self, entries=None, pagination=None):
        if entries is None:
            entries = [_make_dir(), _make_file()]
        if pagination is None:
            pagination = Pagination(total=2, offset=0, limit=115)
        mock_client = MagicMock()
        mock_client.file.find.return_value = (entries, pagination)
        return mock_client

    @patch.object(FindCommand, "_create_client")
    def test_find_table_format(self, mock_create):
        mock_create.return_value = self._make_client_mock()
        parser = build_parser()
        args = parser.parse_args(["find", "test"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            FindCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("testdir/", output)
        self.assertIn("test.txt", output)

    @patch.object(FindCommand, "_create_client")
    def test_find_global_search(self, mock_create):
        """path=None triggers a global search (no cid in API call)."""
        mock_create.return_value = self._make_client_mock()
        parser = build_parser()
        args = parser.parse_args(["find", "keyword"])

        with patch("sys.stdout", new_callable=io.StringIO):
            FindCommand().execute(args)

        call_kwargs = mock_create.return_value.file.find.call_args
        self.assertIsNone(call_kwargs.kwargs["path"])
        self.assertEqual(call_kwargs.args[0], "keyword")

    @patch.object(FindCommand, "_create_client")
    def test_find_with_path(self, mock_create):
        """Providing a path positional arg passes it as the search scope."""
        mock_create.return_value = self._make_client_mock()
        parser = build_parser()
        args = parser.parse_args(["find", "/docs", "keyword"])

        with patch("sys.stdout", new_callable=io.StringIO):
            FindCommand().execute(args)

        call_kwargs = mock_create.return_value.file.find.call_args
        self.assertEqual(call_kwargs.kwargs["path"], "/docs")
        self.assertEqual(call_kwargs.args[0], "keyword")

    @patch.object(FindCommand, "_create_client")
    def test_find_pagination_args(self, mock_create):
        mock_create.return_value = self._make_client_mock()
        parser = build_parser()
        args = parser.parse_args(["find", "--offset", "10", "--limit", "5", "test"])

        with patch("sys.stdout", new_callable=io.StringIO):
            FindCommand().execute(args)

        call_kwargs = mock_create.return_value.file.find.call_args.kwargs
        self.assertEqual(call_kwargs["offset"], 10)
        self.assertEqual(call_kwargs["limit"], 5)

    @patch.object(FindCommand, "_create_client")
    def test_find_json_format(self, mock_create):
        import json

        mock_create.return_value = self._make_client_mock(
            entries=[_make_file(name="report.pdf", id="999")],
            pagination=Pagination(total=1, offset=0, limit=115),
        )
        parser = build_parser()
        args = parser.parse_args(["find", "--format", "json", "report"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            FindCommand().execute(args)

        data = json.loads(mock_out.getvalue())
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["Name"], "report.pdf")
        self.assertEqual(data[0]["ID"], "999")

    @patch.object(FindCommand, "_create_client")
    def test_find_plain_format(self, mock_create):
        mock_create.return_value = self._make_client_mock(
            entries=[_make_file(name="note.txt", id="888")],
            pagination=Pagination(total=1, offset=0, limit=115),
        )
        parser = build_parser()
        args = parser.parse_args(["find", "--format", "plain", "note"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            FindCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("note.txt", output)
        self.assertIn("888", output)

    @patch.object(FindCommand, "_create_client")
    def test_find_empty_results(self, mock_create):
        mock_create.return_value = self._make_client_mock(
            entries=[], pagination=Pagination(total=0, offset=0, limit=115)
        )
        parser = build_parser()
        args = parser.parse_args(["find", "--format", "plain", "nonexistent"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            FindCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("No entries found.", output)

    @patch.object(FindCommand, "_create_client")
    def test_find_pagination_warning(self, mock_create):
        """A warning is printed when total exceeds DEFAULT_PAGE_SIZE."""
        from cli115.client.base import DEFAULT_PAGE_SIZE

        entries = [_make_file(name=f"f{i}.txt", id=str(i)) for i in range(10)]
        mock_create.return_value = self._make_client_mock(
            entries=entries,
            pagination=Pagination(total=DEFAULT_PAGE_SIZE + 1, offset=0, limit=115),
        )
        parser = build_parser()
        args = parser.parse_args(["find", "f"])

        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
                FindCommand().execute(args)

        self.assertIn("Warning", mock_err.getvalue())

    @patch.object(FindCommand, "_create_client")
    def test_find_error_exits(self, mock_create):
        mock_client = MagicMock()
        mock_client.file.find.side_effect = RuntimeError("network error")
        mock_create.return_value = mock_client
        parser = build_parser()
        args = parser.parse_args(["find", "test"])

        with self.assertRaises(SystemExit) as ctx:
            with patch("sys.stderr", new_callable=io.StringIO):
                FindCommand().execute(args)

        self.assertEqual(ctx.exception.code, 1)


def _make_download_info():
    return DownloadInfo(
        url="https://cdn.115.com/test.bin?t=123",
        file_name="test.bin",
        file_size=4096,
        sha1="A" * 40,
        user_agent="Mozilla/5.0",
        referer="https://115.com/",
        cookies="UID=u1; CID=c1; SEID=s1; KID=k1",
    )


class TestDownloadInfoCommand(unittest.TestCase):
    @patch.object(DownloadInfoCommand, "_create_client")
    def test_plain_format(self, mock_create):
        mock_client = MagicMock()
        mock_client.file.download_info.return_value = _make_download_info()
        mock_create.return_value = mock_client
        parser = build_parser()
        args = parser.parse_args(["download-info", "/test.bin"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            DownloadInfoCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("https://cdn.115.com/test.bin?t=123", output)
        self.assertIn("test.bin", output)
        self.assertIn("4096", output)
        self.assertIn("Mozilla/5.0", output)
        self.assertIn("UID=u1", output)

    @patch.object(DownloadInfoCommand, "_create_client")
    def test_json_format(self, mock_create):
        import json

        mock_client = MagicMock()
        mock_client.file.download_info.return_value = _make_download_info()
        mock_create.return_value = mock_client
        parser = build_parser()
        args = parser.parse_args(["download-info", "--format", "json", "/test.bin"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            DownloadInfoCommand().execute(args)

        data = json.loads(mock_out.getvalue())
        self.assertEqual(data["url"], "https://cdn.115.com/test.bin?t=123")
        self.assertEqual(data["file_name"], "test.bin")
        self.assertEqual(data["file_size"], 4096)
        self.assertEqual(data["user_agent"], "Mozilla/5.0")
        self.assertIn("UID", data["cookies"])

    @patch("cli115.cmds.download_info.load_config")
    @patch.object(DownloadInfoCommand, "_create_client")
    def test_aria2c_format(self, mock_create, mock_load_config):
        cfg = configparser.ConfigParser()
        cfg["download"] = {
            "min_split_size": "2M",
            "max_connection": "10",
            "validate_hash": "true",
        }
        mock_load_config.return_value = cfg
        mock_client = MagicMock()
        mock_client.file.download_info.return_value = _make_download_info()
        mock_create.return_value = mock_client
        parser = build_parser()
        args = parser.parse_args(["download-info", "--format", "aria2c", "/test.bin"])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            DownloadInfoCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("aria2c", output)
        self.assertIn("-o", output)
        self.assertIn("test.bin", output)
        self.assertIn("-k2M", output)
        self.assertIn("-x10", output)
        self.assertIn("-s10", output)
        self.assertIn(f"--checksum=sha-1={_make_download_info().sha1}", output)
        self.assertIn("User-Agent: Mozilla/5.0", output)
        self.assertIn("Referer: https://115.com", output)
        self.assertIn("UID=u1", output)
        self.assertIn("https://cdn.115.com/test.bin?t=123", output)


class TestConfigCommand(unittest.TestCase):
    @patch("cli115.cmds.config_cmd.load_config")
    def test_outputs_ini_format(self, mock_load):
        config = configparser.ConfigParser()
        config["general"] = {"user_agent": "TestUA", "credentials": "/tmp/creds"}
        config["download"] = {
            "min_split_size": "2M",
            "max_connection": "10",
            "validate_hash": "true",
        }
        mock_load.return_value = config

        cmd = ConfigCommand()
        args = build_parser().parse_args(["config"])
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            cmd.execute(args)

        output = mock_out.getvalue()
        self.assertIn("[general]", output)
        self.assertIn("[download]", output)
        self.assertIn("user_agent", output)

    @patch("cli115.cmds.config_cmd.load_config")
    def test_outputs_download_config_section(self, mock_load):
        config = configparser.ConfigParser()
        config["general"] = {"credentials": "/tmp", "user_agent": "UA"}
        config["download"] = {
            "min_split_size": "2M",
            "max_connection": "10",
            "validate_hash": "true",
        }
        mock_load.return_value = config

        cmd = ConfigCommand()
        args = build_parser().parse_args(["config"])
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            cmd.execute(args)

        output = mock_out.getvalue()
        self.assertIn("min_split_size", output)
        self.assertIn("max_connection", output)
        self.assertIn("validate_hash", output)

    @patch("cli115.cmds.config_cmd.load_config")
    def test_outputs_default_config_when_no_file(self, mock_load):
        from cli115.cmds.config import load_config as real_load_config

        # Simulate load_config returning defaults (no file on disk)
        mock_load.side_effect = real_load_config
        with patch("cli115.cmds.config.DEFAULT_CONFIG_FILE") as mock_file:
            mock_file.exists.return_value = False
            cmd = ConfigCommand()
            args = build_parser().parse_args(["config"])
            with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                cmd.execute(args)

        output = mock_out.getvalue()
        self.assertIn("[general]", output)
        self.assertIn("[download]", output)
        self.assertIn("2m", output.lower())  # min_split_size default

    @patch("cli115.cmds.config_cmd.load_config")
    def test_config_command_registered_in_cli(self, mock_load):
        config = configparser.ConfigParser()
        config["general"] = {"credentials": "/tmp", "user_agent": "UA"}
        config["download"] = {
            "min_split_size": "2M",
            "max_connection": "10",
            "validate_hash": "true",
        }
        mock_load.return_value = config

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            main(["config"])

        self.assertIn("[general]", mock_out.getvalue())


if __name__ == "__main__":
    unittest.main()
