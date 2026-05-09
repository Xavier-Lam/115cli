import json
from datetime import datetime
from unittest.mock import MagicMock, patch

from cli115.client.models import Directory, File, ShareInfo
from cli115.cmds.share import (
    ShareInfoCommand,
    ShareListCommand,
    ShareSaveCommand,
    ShareStatCommand,
)
from tests.helpers import make_lazy, make_parser


def _make_share_info(receive_code: str = "azhy") -> ShareInfo:
    return ShareInfo(
        share_code="swzadyu3zs9",
        share_id="308465423",
        title="sample share",
        owner_id="337137737",
        owner_name="test-user",
        has_password=bool(receive_code),
        receive_code=receive_code,
        receive_count=337,
        item_count=1,
        total_size=42056430,
        created_time=datetime(2024, 6, 22, 10, 0, 0),
        expire_time=None,
        is_available=True,
    )


def _make_dir(name: str = "docs") -> Directory:
    return Directory(
        id="100",
        parent_id="0",
        name=name,
        path=f"/{name}",
        pickcode="pc-dir",
        created_time=datetime(2024, 6, 22, 10, 0, 0),
        modified_time=datetime(2024, 6, 22, 10, 0, 0),
        open_time=None,
        file_count=2,
    )


def _make_file(name: str = "guide.txt", file_id: str = "201") -> File:
    return File(
        id=file_id,
        parent_id="100",
        name=name,
        path=f"/docs/{name}",
        pickcode="pc-file",
        created_time=datetime(2024, 6, 22, 10, 0, 0),
        modified_time=datetime(2024, 6, 22, 10, 0, 0),
        open_time=None,
        size=4096,
        sha1="ABC123",
        file_type="txt",
        starred=False,
    )


class TestShareInfoCommand:
    @patch.object(ShareInfoCommand, "_create_client")
    def test_info(self, mock_create_client, capsys):
        mock_client = MagicMock()
        mock_client.share.info.return_value = _make_share_info()
        mock_create_client.return_value = mock_client

        parser, cmds = make_parser()
        args = parser.parse_args(
            [
                "share",
                "info",
                "https://115cdn.com/s/swzadyu3zs9?password=azhy",
                "--format",
                "json",
            ]
        )
        cmds["share"].execute(args)

        mock_client.share.info.assert_called_once_with(
            "swzadyu3zs9",
            password="azhy",
        )

        data = json.loads(capsys.readouterr().out)
        assert data["Share Code"] == "swzadyu3zs9"
        assert data["Share ID"] == "308465423"
        assert data["Title"] == "sample share"
        assert data["Owner"] == "test-user"
        assert data["Password"] == "azhy"
        assert data["Item Count"] == 1
        assert data["Total Size"] == 42056430
        assert data["Available"] is True

    @patch.object(ShareInfoCommand, "_create_client")
    def test_info_with_password(self, mock_create_client):
        mock_client = MagicMock()
        mock_client.share.info.return_value = _make_share_info("wxyz")
        mock_create_client.return_value = mock_client

        parser, cmds = make_parser()
        args = parser.parse_args(
            [
                "share",
                "info",
                "https://115cdn.com/s/swzadyu3zs9?password=azhy",
                "-p",
                "wxyz",
            ]
        )
        cmds["share"].execute(args)

        mock_client.share.info.assert_called_once_with(
            "swzadyu3zs9",
            password="wxyz",
        )


class TestShareListCommand:
    @patch.object(ShareListCommand, "_create_client")
    def test_list(self, mock_create_client, capsys):
        mock_client = MagicMock()
        mock_client.share.list.return_value = make_lazy([_make_dir(), _make_file()])
        mock_create_client.return_value = mock_client

        parser, cmds = make_parser()
        args = parser.parse_args(
            [
                "share",
                "list",
                "https://115cdn.com/s/swzadyu3zs9?password=azhy",
                "/docs",
                "--format",
                "json",
            ]
        )
        cmds["share"].execute(args)

        mock_client.share.list.assert_called_once_with(
            "swzadyu3zs9",
            password="azhy",
            path="/docs",
        )

        data = json.loads(capsys.readouterr().out)
        assert len(data) == 2
        assert data[0]["Name"] == "docs/"
        assert data[0]["Type"] == "dir"
        assert data[1]["Name"] == "guide.txt"
        assert data[1]["Type"] == "txt"
        assert data[1]["Size"] == "4.0 KB"

    @patch.object(ShareListCommand, "_create_client")
    def test_list_with_password(self, mock_create_client):
        mock_client = MagicMock()
        mock_client.share.list.return_value = make_lazy([])
        mock_create_client.return_value = mock_client

        parser, cmds = make_parser()
        args = parser.parse_args(
            [
                "share",
                "list",
                "https://115cdn.com/s/swzadyu3zs9?password=azhy",
                "-p",
                "wxyz",
            ]
        )
        cmds["share"].execute(args)

        mock_client.share.list.assert_called_once_with(
            "swzadyu3zs9",
            password="wxyz",
            path="/",
        )


class TestShareStatCommand:
    @patch.object(ShareStatCommand, "_create_client")
    def test_stat(self, mock_create_client, capsys):
        mock_client = MagicMock()
        mock_client.share.stat.return_value = _make_file()
        mock_create_client.return_value = mock_client

        parser, cmds = make_parser()
        args = parser.parse_args(
            [
                "share",
                "stat",
                "https://115cdn.com/s/swzadyu3zs9?password=azhy",
                "/docs/guide.txt",
                "--format",
                "json",
            ]
        )
        cmds["share"].execute(args)

        mock_client.share.stat.assert_called_once_with(
            "swzadyu3zs9",
            "/docs/guide.txt",
            password="azhy",
        )

        data = json.loads(capsys.readouterr().out)
        assert data["Name"] == "guide.txt"
        assert data["ID"] == "201"
        assert data["Path"] == "/docs/guide.txt"
        assert data["Type"] == "File"
        assert data["Size"] == 4096


class TestShareSaveCommand:
    @patch.object(ShareSaveCommand, "_create_client")
    def test_save_directory(self, mock_create_client, capsys):
        mock_client = MagicMock()
        mock_client.share.stat.return_value = _make_dir(name="docs")
        mock_client.share.list.return_value = make_lazy(
            [
                _make_dir(name="books"),
                _make_file(name="guide.txt", file_id="201"),
            ]
        )
        mock_create_client.return_value = mock_client

        parser, cmds = make_parser()
        args = parser.parse_args(
            [
                "share",
                "save",
                "https://115cdn.com/s/swzadyu3zs9?password=azhy",
                "/docs",
                "--dest",
                "/backup",
            ]
        )
        cmds["share"].execute(args)

        mock_client.share.stat.assert_called_once_with(
            "swzadyu3zs9",
            "/docs",
            password="azhy",
        )
        mock_client.share.list.assert_called_once_with(
            "swzadyu3zs9",
            password="azhy",
            path="/docs",
        )
        mock_client.share.save.assert_called_once_with(
            "swzadyu3zs9",
            ["100", "201"],
            password="azhy",
            dest_dir="/backup",
        )

        assert "Saved 2 item(s) to /backup" in capsys.readouterr().out

    @patch.object(ShareSaveCommand, "_create_client")
    def test_save_with_patterns(self, mock_create_client):
        mock_client = MagicMock()
        mock_client.share.stat.return_value = _make_dir(name="docs")
        mock_client.share.list.return_value = make_lazy(
            [
                _make_file(name="guide.txt", file_id="201"),
                _make_file(name="notes.md", file_id="202"),
            ]
        )
        mock_create_client.return_value = mock_client

        parser, cmds = make_parser()
        args = parser.parse_args(
            [
                "share",
                "save",
                "https://115cdn.com/s/swzadyu3zs9?password=azhy",
                "/docs",
                "--dest",
                "/backup",
                "--include",
                "*.txt",
                "--exclude",
                "notes.*",
            ]
        )
        cmds["share"].execute(args)

        mock_client.share.save.assert_called_once_with(
            "swzadyu3zs9",
            ["201"],
            password="azhy",
            dest_dir="/backup",
        )

    @patch.object(ShareSaveCommand, "_create_client")
    def test_save_single_file(self, mock_create_client):
        mock_client = MagicMock()
        mock_client.share.stat.return_value = _make_file(
            name="guide.txt",
            file_id="201",
        )
        mock_create_client.return_value = mock_client

        parser, cmds = make_parser()
        args = parser.parse_args(
            [
                "share",
                "save",
                "https://115cdn.com/s/swzadyu3zs9?password=azhy",
                "/docs/guide.txt",
            ]
        )
        cmds["share"].execute(args)

        mock_client.share.list.assert_not_called()
        mock_client.share.save.assert_called_once_with(
            "swzadyu3zs9",
            ["201"],
            password="azhy",
            dest_dir="/",
        )

    @patch.object(ShareSaveCommand, "_create_client")
    def test_save_no_match(self, mock_create_client, capsys):
        mock_client = MagicMock()
        mock_client.share.stat.return_value = _make_dir(name="docs")
        mock_client.share.list.return_value = make_lazy(
            [
                _make_file(name="guide.txt", file_id="201"),
                _make_file(name="notes.md", file_id="202"),
            ]
        )
        mock_create_client.return_value = mock_client

        parser, cmds = make_parser()
        args = parser.parse_args(
            [
                "share",
                "save",
                "https://115cdn.com/s/swzadyu3zs9?password=azhy",
                "/docs",
                "--include",
                "*.pdf",
            ]
        )
        cmds["share"].execute(args)

        mock_client.share.save.assert_not_called()
        assert "No entries matched include/exclude patterns" in capsys.readouterr().out
