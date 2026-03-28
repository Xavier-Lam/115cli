from unittest.mock import patch

from cli115.cli import load_config, DEFAULT_CREDENTIALS_DIR
from cli115.client.webapi import DEFAULT_USER_AGENT


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
