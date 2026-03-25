import configparser
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from cli115.cli import build_parser
from cli115.cmds.auth import AuthCommand, _parse_cookie_string
from cli115.cmds.config import CURRENT_CREDENTIAL_FILE


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
    def _mock_client(self, user_name="TestUser", user_id="12345"):
        mock_client = MagicMock()
        mock_client.account.info.return_value = MagicMock(
            user_name=user_name, user_id=user_id
        )
        return mock_client

    @patch("cli115.cmds.auth.create_client")
    @patch("cli115.cmds.auth.save_cookie_credential")
    def test_saves_credential(self, mock_save, mock_create_client):
        mock_save.return_value = Path("/tmp/cookie_u1.json")
        mock_create_client.return_value = self._mock_client()
        parser = build_parser()
        args = parser.parse_args(
            ["auth", "cookie", "u1", "UID=u1; CID=c1; SEID=s1; KID=k1"]
        )

        with patch("sys.stdout", new_callable=io.StringIO):
            AuthCommand().execute(args)

        mock_save.assert_called_once()
        call_args = mock_save.call_args
        self.assertEqual(call_args[0][0], "u1")
        self.assertIn("UID", call_args[0][1])

    @patch("cli115.cmds.auth.create_client")
    @patch("cli115.cmds.auth.save_cookie_credential")
    def test_validates_saved_credential(self, mock_save, mock_create_client):
        mock_save.return_value = Path("/tmp/cookie_u1.json")
        mock_create_client.return_value = self._mock_client("TestUser", "12345")
        parser = build_parser()
        args = parser.parse_args(
            ["auth", "cookie", "u1", "UID=u1; CID=c1; SEID=s1; KID=k1"]
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            AuthCommand().execute(args)

        output = mock_out.getvalue()
        self.assertIn("TestUser", output)
        self.assertIn("12345", output)

    @patch("cli115.cmds.auth.create_client")
    @patch("cli115.cmds.config.save_config")
    @patch("cli115.cmds.config.load_config")
    def test_updates_credential_when_already_exists(
        self, mock_load_config, _mock_save_config, mock_create_client
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            cred_dir = Path(tmpdir)
            config = configparser.ConfigParser()
            config["general"] = {"credentials": str(cred_dir)}
            mock_load_config.return_value = config
            mock_create_client.return_value = self._mock_client()

            existing_path = cred_dir / "cookie_u1.json"
            existing_path.write_text(
                json.dumps(
                    {
                        "type": "cookie",
                        "uid": "u1",
                        "cookies": {
                            "UID": "u1",
                            "CID": "old_c",
                            "SEID": "old_s",
                            "KID": "old_k",
                        },
                    }
                )
            )
            (cred_dir / CURRENT_CREDENTIAL_FILE).write_text("cookie_u1.json")

            parser = build_parser()
            args = parser.parse_args(
                ["auth", "cookie", "u1", "UID=u1; CID=new_c; SEID=new_s; KID=new_k"]
            )
            with patch("sys.stdout", new_callable=io.StringIO):
                AuthCommand().execute(args)

            with open(existing_path) as f:
                data = json.load(f)
            self.assertEqual(data["cookies"]["CID"], "new_c")
            self.assertEqual(data["cookies"]["SEID"], "new_s")

    @patch("cli115.cmds.auth.create_client")
    @patch("cli115.cmds.config.save_config")
    @patch("cli115.cmds.config.load_config")
    def test_change_user_updates_active_credential(
        self, mock_load_config, _mock_save_config, mock_create_client
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            cred_dir = Path(tmpdir)
            config = configparser.ConfigParser()
            config["general"] = {"credentials": str(cred_dir)}
            mock_load_config.return_value = config
            mock_create_client.return_value = self._mock_client()

            (cred_dir / "cookie_u1.json").write_text(
                json.dumps(
                    {
                        "type": "cookie",
                        "uid": "u1",
                        "cookies": {
                            "UID": "u1",
                            "CID": "c1",
                            "SEID": "s1",
                            "KID": "k1",
                        },
                    }
                )
            )
            (cred_dir / CURRENT_CREDENTIAL_FILE).write_text("cookie_u1.json")

            parser = build_parser()
            args = parser.parse_args(
                ["auth", "cookie", "u2", "UID=u2; CID=c2; SEID=s2; KID=k2"]
            )
            with patch("sys.stdout", new_callable=io.StringIO):
                AuthCommand().execute(args)

            current = (cred_dir / CURRENT_CREDENTIAL_FILE).read_text().strip()
            self.assertEqual(current, "cookie_u2.json")


if __name__ == "__main__":
    unittest.main()
