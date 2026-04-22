import json
from datetime import datetime
from unittest.mock import MagicMock, patch

from cli115.cli import build_parser, load_config
from cli115.client.models import (
    CloudTask,
    DownloadQuota,
    TaskFilter,
    TaskStatus,
)
from cli115.cmds.download import (
    DownloadAddCommand,
    DownloadClearCommand,
    DownloadDeleteCommand,
    DownloadStatusCommand,
    DownloadListCommand,
    DownloadQuotaCommand,
    DownloadRetryCommand,
)
from cli115.credentials import CredentialManager
from tests.helpers import make_lazy


def _build_parser():
    cfg = load_config()
    cm = CredentialManager(cfg)
    return build_parser(cfg, cm)


def _make_task(
    info_hash="abc123hash",
    name="test-download.png",
    size=2048,
    status=TaskStatus.DOWNLOADING,
    percent_done=50.0,
    file_id="",
):
    return CloudTask(
        info_hash=info_hash,
        name=name,
        size=size,
        status=status,
        percent_done=percent_done,
        url="https://example.com/file.png",
        file_id=file_id,
        pick_code="",
        folder_id="0",
        add_time=datetime(2025, 1, 1),
    )


class TestDownloadCommand:
    @patch.object(DownloadQuotaCommand, "_create_client")
    def test_quota(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_client.download.quota.return_value = DownloadQuota(quota=2985, total=3000)
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(["download", "quota", "--format", "json"])
        cmds["download"].execute(args)

        data = json.loads(capsys.readouterr().out)
        assert data["Remaining"] == 2985
        assert data["Total"] == 3000

    @patch.object(DownloadListCommand, "_create_client")
    def test_list(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_client.download.list.return_value = make_lazy([_make_task()])
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(["download", "list", "--format", "json"])
        cmds["download"].execute(args)

        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1
        assert data[0]["Hash"] == "abc123hash"
        assert data[0]["Name"] == "test-download.png"

        mock_client = MagicMock()
        mock_client.download.list.return_value = make_lazy(
            [
                _make_task(status=TaskStatus.COMPLETED, percent_done=100.0),
            ]
        )
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(
            ["download", "list", "--filter", "completed", "--format", "json"]
        )
        cmds["download"].execute(args)

        mock_client.download.list.assert_called_once_with(filter=TaskFilter.COMPLETED)
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1

    @patch.object(DownloadDeleteCommand, "_create_client")
    def test_delete(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(["download", "delete", "hash1", "hash2"])
        cmds["download"].execute(args)

        mock_client.download.delete.assert_called_once_with("hash1", "hash2")
        output = capsys.readouterr().out
        assert "hash1" in output
        assert "hash2" in output

    @patch.object(DownloadAddCommand, "_create_client")
    def test_add_single(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_client.download.add_url.return_value = _make_task()
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(["download", "add", "https://example.com/file.png"])
        cmds["download"].execute(args)

        mock_client.download.add_url.assert_called_once_with(
            "https://example.com/file.png", dest_dir=None
        )
        assert "abc123hash" in capsys.readouterr().out

    @patch.object(DownloadAddCommand, "_create_client")
    def test_add_single_with_dest(self, mock_create):
        mock_client = MagicMock()
        mock_client.download.add_url.return_value = _make_task()
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(
            ["download", "add", "--dest", "/my/folder", "https://example.com/file.png"]
        )
        cmds["download"].execute(args)

        mock_client.download.add_url.assert_called_once_with(
            "https://example.com/file.png", dest_dir="/my/folder"
        )

    @patch.object(DownloadAddCommand, "_create_client")
    def test_add_batch(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_client.download.add_urls.return_value = [
            _make_task(info_hash="hash1"),
            _make_task(info_hash="hash2"),
        ]
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(
            [
                "download",
                "add",
                "https://example.com/a.png",
                "https://example.com/b.png",
            ]
        )
        cmds["download"].execute(args)

        mock_client.download.add_urls.assert_called_once_with(
            "https://example.com/a.png",
            "https://example.com/b.png",
            dest_dir=None,
        )
        output = capsys.readouterr().out
        assert "hash1" in output
        assert "hash2" in output

    @patch.object(DownloadClearCommand, "_create_client")
    def test_clear_all(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(["download", "clear"])
        cmds["download"].execute(args)

        mock_client.download.clear.assert_called_once_with(filter=None)
        assert "all" in capsys.readouterr().out

    @patch.object(DownloadClearCommand, "_create_client")
    def test_clear_completed(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(["download", "clear", "--filter", "completed"])
        cmds["download"].execute(args)

        mock_client.download.clear.assert_called_once_with(filter=TaskFilter.COMPLETED)
        assert "completed" in capsys.readouterr().out

    @patch.object(DownloadStatusCommand, "_create_client")
    def test_info(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_client.download.list.return_value = make_lazy(
            [_make_task(info_hash="abc123hash", status=TaskStatus.DOWNLOADING)]
        )
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(
            ["download", "status", "abc123hash", "--format", "json"]
        )
        cmds["download"].execute(args)

        data = json.loads(capsys.readouterr().out)
        assert data["Hash"] == "abc123hash"
        assert data["Name"] == "test-download.png"

    @patch.object(DownloadRetryCommand, "_create_client")
    def test_retry(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        parser, cmds = _build_parser()
        args = parser.parse_args(["download", "retry", "hash1"])
        cmds["download"].execute(args)

        mock_client.download.retry.assert_called_once_with("hash1")
        output = capsys.readouterr().out
        assert "hash1" in output
