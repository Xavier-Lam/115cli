import configparser
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from cli115.cmds.config import (
    CURRENT_CREDENTIAL_FILE,
    get_credentials_dir,
    load_config,
    load_current_credential,
    save_config,
    save_cookie_credential,
)


class TestLoadConfig(unittest.TestCase):
    @patch("cli115.cmds.config.DEFAULT_CONFIG_FILE")
    def test_returns_defaults_when_no_file(self, mock_file):
        mock_file.exists.return_value = False
        config = load_config()
        self.assertIn("general", config)
        self.assertIn("credentials", config["general"])

    @patch("cli115.cmds.config.DEFAULT_CONFIG_FILE")
    def test_reads_existing_config(self, mock_file):
        mock_file.exists.return_value = True
        with patch.object(configparser.ConfigParser, "read"):
            config = load_config()
            self.assertIn("general", config)


class TestSaveConfig(unittest.TestCase):
    @patch("cli115.cmds.config.DEFAULT_CONFIG_FILE", Path("/tmp/test_config.ini"))
    @patch("cli115.cmds.config.get_config_dir")
    def test_save_creates_dir_and_writes(self, mock_dir):
        mock_path = unittest.mock.MagicMock()
        mock_dir.return_value = mock_path
        config = configparser.ConfigParser()
        config["general"] = {"credentials": "/tmp/creds"}

        m = unittest.mock.mock_open()
        with patch("builtins.open", m):
            save_config(config)

        mock_path.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        m.assert_called_once()


class TestGetCredentialsDir(unittest.TestCase):
    def test_returns_path_from_config(self):
        config = configparser.ConfigParser()
        config["general"] = {"credentials": "/custom/path"}
        result = get_credentials_dir(config)
        self.assertEqual(result, Path("/custom/path"))


class TestSaveCookieCredential(unittest.TestCase):
    @patch("cli115.cmds.config.save_config")
    @patch("cli115.cmds.config.load_config")
    def test_saves_credential_file(self, mock_load, mock_save):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            config = configparser.ConfigParser()
            config["general"] = {"credentials": tmpdir}
            mock_load.return_value = config

            cookies = {"UID": "u1", "CID": "c1", "SEID": "s1", "KID": "k1"}
            result = save_cookie_credential("testuser", cookies)

            self.assertTrue(result.exists())
            self.assertEqual(result.name, "cookie_testuser.json")

            with open(result) as f:
                data = json.load(f)
            self.assertEqual(data["type"], "cookie")
            self.assertEqual(data["uid"], "testuser")
            self.assertEqual(data["cookies"], cookies)

            current = Path(tmpdir) / CURRENT_CREDENTIAL_FILE
            self.assertEqual(current.read_text(), "cookie_testuser.json")


class TestLoadCurrentCredential(unittest.TestCase):
    @patch("cli115.cmds.config.load_config")
    def test_raises_when_no_current_credential(self, mock_load):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            config = configparser.ConfigParser()
            config["general"] = {"credentials": tmpdir}
            mock_load.return_value = config

            with self.assertRaises(FileNotFoundError):
                load_current_credential()

    @patch("cli115.cmds.config.load_config")
    def test_loads_existing_credential(self, mock_load):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            config = configparser.ConfigParser()
            config["general"] = {"credentials": tmpdir}
            mock_load.return_value = config

            cred_data = {"type": "cookie", "uid": "u1", "cookies": {"UID": "u1"}}
            cred_file = Path(tmpdir) / "cookie_u1.json"
            with open(cred_file, "w") as f:
                json.dump(cred_data, f)
            current_file = Path(tmpdir) / CURRENT_CREDENTIAL_FILE
            current_file.write_text("cookie_u1.json")

            result = load_current_credential()
            self.assertEqual(result, cred_data)

    @patch("cli115.cmds.config.load_config")
    def test_raises_when_credential_file_missing(self, mock_load):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            config = configparser.ConfigParser()
            config["general"] = {"credentials": tmpdir}
            mock_load.return_value = config

            current_file = Path(tmpdir) / CURRENT_CREDENTIAL_FILE
            current_file.write_text("cookie_missing.json")

            with self.assertRaises(FileNotFoundError):
                load_current_credential()


if __name__ == "__main__":
    unittest.main()
