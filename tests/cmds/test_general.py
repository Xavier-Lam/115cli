from configparser import ConfigParser
import json
from datetime import datetime
from unittest.mock import MagicMock, patch

from cli115.cli import build_parser, load_config
from cli115.client.models import AccountInfo
from cli115.credentials import CredentialManager


class TestAccountCommand:
    @patch("cli115.cmds.account.AccountCommand._create_client")
    def test_account_info(self, mock_create, capsys):
        mock_client = MagicMock()
        mock_client.account.info.return_value = AccountInfo(
            user_name="testuser",
            user_id=12345,
            vip=True,
            expire=datetime(2025, 1, 1),
        )
        mock_create.return_value = mock_client

        cfg = load_config()
        cm = CredentialManager(cfg)
        parser, commands = build_parser(cfg, cm)
        args = parser.parse_args(["account", "--format", "json"])
        commands["account"].execute(args)

        data = json.loads(capsys.readouterr().out)
        assert data["Username"] == "testuser"
        assert data["User ID"] == 12345


class TestConfigCommand:
    @patch("cli115.cli.load_config")
    def test_outputs_ini_sections(self, mock_load, capsys):
        cfg = ConfigParser()
        cfg["general"] = {"user_agent": "TestUA", "credentials": "/tmp/creds"}
        cfg["download"] = {"min_split_size": "20M", "max_connection": "10"}

        cm = CredentialManager(cfg)
        parser, commands = build_parser(cfg, cm)
        args = parser.parse_args(["config"])
        commands["config"].execute(args)

        output = capsys.readouterr().out
        assert "[general]" in output
        assert "[download]" in output
        assert "user_agent" in output
        assert "TestUA" in output
        assert "min_split_size" in output
        assert "20m" in output.lower()
        assert "max_connection" in output
        assert "10" in output

    @patch("cli115.cli.DEFAULT_CONFIG_FILE")
    def test_outputs_default_when_no_file(self, mock_file, capsys):
        mock_file.exists.return_value = False
        cfg = load_config()
        cm = CredentialManager(cfg)
        parser, commands = build_parser(cfg, cm)
        args = parser.parse_args(["config"])
        commands["config"].execute(args)

        output = capsys.readouterr().out
        assert "[general]" in output
        assert "[download]" in output
        assert "2m" in output.lower()
