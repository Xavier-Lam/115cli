import argparse
import pytest
from unittest.mock import MagicMock, patch

from cli115.cli import build_parser, load_config, main, DEFAULT_CREDENTIALS_DIR
from cli115.client.webapi import DEFAULT_USER_AGENT
from cli115.cmds.ls import LsCommand
from cli115.credentials import CredentialManager
from cli115.exceptions import CommandLineError
from tests.helpers import make_lazy


class TestLoadConfig:
    @patch("cli115.cli.DEFAULT_CONFIG_FILE")
    def test_returns_defaults_when_file_not_exists(self, mock_file):
        mock_file.exists.return_value = False
        cfg = load_config()

        assert cfg["general"]["credentials"] == str(DEFAULT_CREDENTIALS_DIR)
        assert cfg["general"]["user_agent"] == DEFAULT_USER_AGENT
        assert cfg["download"]["min_split_size"] == "2M"
        assert cfg["download"]["max_connection"] == "2"

    def test_reads_config_file_when_exists(self, tmp_path):
        config_file = tmp_path / "config.ini"
        config_file.write_text(
            "[general]\ncredentials = /custom/creds\nuser_agent = CustomUA\n"
            "[download]\nmin_split_size = 10M\nmax_connection = 5\n"
        )
        with patch("cli115.cli.DEFAULT_CONFIG_FILE", new=config_file):
            cfg = load_config()

        assert cfg["general"]["credentials"] == "/custom/creds"
        assert cfg["general"]["user_agent"] == "CustomUA"
        assert cfg["download"]["min_split_size"] == "10M"
        assert cfg["download"]["max_connection"] == "5"

    def test_missing_keys_filled_with_defaults_when_file_partial(self, tmp_path):
        config_file = tmp_path / "config.ini"
        config_file.write_text("[general]\ncredentials = /only/this\n")
        with patch("cli115.cli.DEFAULT_CONFIG_FILE", new=config_file):
            cfg = load_config()

        assert cfg["general"]["credentials"] == "/only/this"
        assert cfg["general"]["user_agent"] == DEFAULT_USER_AGENT
        assert cfg["download"]["min_split_size"] == "2M"
        assert cfg["download"]["max_connection"] == "2"


class TestBuildParser:
    def test_all_commands_registered(self):
        cfg = load_config()
        _, commands = build_parser(cfg, CredentialManager(cfg))
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
            assert cmd in commands


class TestMainEntryPoint:
    @patch.object(LsCommand, "_create_client")
    def test_dispatch_to_command(self, mock_create):
        mock_client = MagicMock()
        mock_client.file.list.return_value = make_lazy([])
        mock_create.return_value = mock_client

        main(["ls", "/"])

        mock_client.file.list.assert_called_once()

    @patch.object(LsCommand, "execute", side_effect=CommandLineError("bad thing"))
    def test_command_line_error_caught(self, mock_execute, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["ls", "/"])

        assert exc_info.value.code == 1
        assert "Error: bad thing" in capsys.readouterr().err

    def test_login_required_command_errors_when_not_logged_in(self, tmp_path, capsys):
        # Ensure the credentials directory is an empty temp path so no active
        # user exists and the command should error out.
        with (
            patch("cli115.cli.DEFAULT_CONFIG_FILE", new=tmp_path / "config.ini"),
            patch("cli115.cli.DEFAULT_CREDENTIALS_DIR", new=tmp_path / "credentials"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main(["ls", "/"])

        assert exc_info.value.code == 1
        assert "Error: No active user" in capsys.readouterr().err


class TestPaginationCommand:
    def _make_cmd(self, default_page_size=3):
        # Concrete subclass using LsCommand (which extends PaginationCommand)
        cmd = LsCommand.__new__(LsCommand)
        cmd._default_page_size = default_page_size
        return cmd

    def _args(self, limit=None, offset=None):
        return argparse.Namespace(limit=limit, offset=offset)

    def test_pagination(self):
        cmd = self._make_cmd(default_page_size=2)
        result = cmd.apply_pagination([10, 20, 30, 40], self._args())
        assert result == [10, 20]

        cmd = self._make_cmd()
        result = cmd.apply_pagination([1, 2, 3, 4, 5], self._args(limit=4))
        assert result == [1, 2, 3, 4]

        cmd = self._make_cmd()
        result = cmd.apply_pagination([1, 2, 3, 4, 5], self._args(offset=2))
        assert result == [3, 4, 5]

        cmd = self._make_cmd()
        result = cmd.apply_pagination([1, 2, 3, 4, 5], self._args(limit=2, offset=1))
        assert result == [2, 3]

    def test_limit_warnings(self, capsys):
        cmd = self._make_cmd(default_page_size=2)
        cmd.apply_pagination([1, 2, 3], self._args())
        err = capsys.readouterr().err
        assert "Warning" in err
        assert "3" in err

        cmd = self._make_cmd(default_page_size=2)
        cmd.apply_pagination([1, 2, 3], self._args(limit=2))
        assert capsys.readouterr().err == ""

        cmd = self._make_cmd(default_page_size=2)
        cmd.apply_pagination([1, 2, 3], self._args(offset=1))
        assert capsys.readouterr().err == ""

        cmd = self._make_cmd(default_page_size=10)
        cmd.apply_pagination([1, 2, 3], self._args())
        assert capsys.readouterr().err == ""

    def test_register_adds_limit_and_offset_arguments(self):
        cmd = self._make_cmd()
        parser = argparse.ArgumentParser()
        cmd.register(parser)
        args = parser.parse_args(["--limit", "5", "--offset", "10"])
        assert args.limit == 5
        assert args.offset == 10
