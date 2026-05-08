import json
from datetime import datetime
from unittest.mock import MagicMock, patch

from cli115.client.models import ShareInfo
from cli115.cmds.share import ShareInfoCommand
from tests.helpers import make_parser


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
