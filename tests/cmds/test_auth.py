import configparser
import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from cli115.auth.cookie import CookieAuth
from cli115.cli import build_parser
from cli115.client.models import AccountInfo
from cli115.credentials import CredentialManager, CredType, CURRENT_CREDENTIAL_FILE
from cli115.exceptions import CredentialError


COOKIE_STRING = "UID=user1; CID=cid1; SEID=seid1; KID=kid1"
COOKIE_VALUES = {"UID": "user1", "CID": "cid1", "SEID": "seid1", "KID": "kid1"}
COOKIE2_VALUES = {"UID": "u2", "CID": "c2", "SEID": "s2", "KID": "k2"}


def _make_config(cred_dir):
    config = configparser.ConfigParser()
    config["general"] = {"credentials": str(cred_dir)}
    return config


def _make_account(user_name="testuser", user_id=12345):
    return AccountInfo(
        user_name=user_name,
        user_id=user_id,
        vip=True,
        expire=datetime(2025, 1, 1),
    )


def _setup_cm(tmp_path):
    config = _make_config(tmp_path)
    return CredentialManager(config), config


class TestAuthCookieCommand:
    @patch("cli115.cmds.auth.create_client")
    def test_cookie_string_stores_credentials(
        self, mock_create_client, tmp_path, capsys
    ):
        cm, cfg = _setup_cm(tmp_path)
        mock_client = MagicMock()
        mock_client.account.info.return_value = _make_account()
        mock_create_client.return_value = mock_client

        parser, commands = build_parser(config=cfg, credential_manager=cm)
        args = parser.parse_args(["auth", "cookie", COOKIE_STRING])
        commands["auth"].execute(args)

        # CookieAuth constructor must receive the parsed cookie fields
        auth_arg = mock_create_client.call_args[0][0]
        assert isinstance(auth_arg, CookieAuth)
        assert auth_arg.get_cookies() == COOKIE_VALUES

        # Credentials must be persisted to disk
        cred_file = tmp_path / "testuser.json"
        assert cred_file.exists()
        data = json.loads(cred_file.read_text())
        assert data["cookie"] == COOKIE_VALUES

        # Current user must NOT be changed by auth command
        assert not (tmp_path / CURRENT_CREDENTIAL_FILE).exists()

        out = capsys.readouterr().out
        assert "Credentials stored" in out
        assert "testuser" in out
        assert "12345" in out

    @patch("cli115.cmds.auth.create_client")
    def test_cookie_ids_stores_credentials(self, mock_create_client, tmp_path, capsys):
        cm, cfg = _setup_cm(tmp_path)
        mock_client = MagicMock()
        mock_client.account.info.return_value = _make_account()
        mock_create_client.return_value = mock_client

        parser, commands = build_parser(config=cfg, credential_manager=cm)
        args = parser.parse_args(
            [
                "auth",
                "cookie",
                "--uid",
                "user1",
                "--cid",
                "cid1",
                "--seid",
                "seid1",
                "--kid",
                "kid1",
            ]
        )
        commands["auth"].execute(args)

        # CookieAuth constructor must receive the right individual values
        auth_arg = mock_create_client.call_args[0][0]
        assert isinstance(auth_arg, CookieAuth)
        assert auth_arg.get_cookies() == COOKIE_VALUES

        cred_file = tmp_path / "testuser.json"
        assert cred_file.exists()
        data = json.loads(cred_file.read_text())
        assert data["cookie"] == COOKIE_VALUES

        # Current user must NOT be changed by auth command
        assert not (tmp_path / CURRENT_CREDENTIAL_FILE).exists()

        out = capsys.readouterr().out
        assert "Credentials stored" in out
        assert "testuser" in out


class TestAuthValidateCommand:
    @patch("cli115.cmds.base.create_client")
    def test_validate_gets_correct_credential_and_validates(
        self, mock_create_client, tmp_path, capsys
    ):
        cm, cfg = _setup_cm(tmp_path)
        # Pre-store credentials for the target user
        cm.save_credential("testuser", CredType.COOKIE, COOKIE_VALUES)

        mock_client = MagicMock()
        mock_client.account.info.return_value = _make_account()
        mock_create_client.return_value = mock_client

        parser, commands = build_parser(config=cfg, credential_manager=cm)
        args = parser.parse_args(["auth", "validate", "testuser"])
        commands["auth"].execute(args)

        # Must retrieve and pass the stored cookie to the client
        auth_arg = mock_create_client.call_args[0][0]
        assert isinstance(auth_arg, CookieAuth)
        assert auth_arg.get_cookies() == COOKIE_VALUES

        out = capsys.readouterr().out
        assert "Credentials valid" in out
        assert "testuser" in out


class TestLoginCookieCommand:
    @patch("cli115.cmds.auth.create_client")
    def test_login_sets_current_user(self, mock_create_client, tmp_path, capsys):
        cm, cfg = _setup_cm(tmp_path)
        mock_client = MagicMock()
        mock_client.account.info.return_value = _make_account()
        mock_create_client.return_value = mock_client

        parser, commands = build_parser(config=cfg, credential_manager=cm)
        args = parser.parse_args(["login", "cookie", COOKIE_STRING])
        commands["login"].execute(args)

        current_file = tmp_path / CURRENT_CREDENTIAL_FILE
        assert current_file.exists()
        assert current_file.read_text().strip() == "testuser"

        out = capsys.readouterr().out
        assert "Authenticated as" in out
        assert "testuser" in out

    @patch("cli115.cmds.auth.create_client")
    def test_login_persists_across_multiple_cli_calls(
        self, mock_create_client, tmp_path, capsys
    ):
        cm, cfg = _setup_cm(tmp_path)
        mock_client = MagicMock()
        mock_client.account.info.return_value = _make_account()
        mock_create_client.return_value = mock_client

        parser, commands = build_parser(config=cfg, credential_manager=cm)
        args = parser.parse_args(["login", "cookie", COOKIE_STRING])
        commands["login"].execute(args)

        cm = CredentialManager(cfg)
        with patch("cli115.cmds.base.create_client") as mock_base_create:
            mock_base_create.return_value = mock_client
            parser, commands = build_parser(config=cfg, credential_manager=cm)
            args = parser.parse_args(["account"])
            commands["account"].execute(args)

        auth_arg = mock_base_create.call_args[0][0]
        assert isinstance(auth_arg, CookieAuth)
        assert auth_arg.get_cookies() == COOKIE_VALUES


class TestLoginSwitchCommand:
    @patch("cli115.cmds.base.create_client")
    def test_switch_changes_current_user(self, mock_create_client, tmp_path, capsys):
        cm, cfg = _setup_cm(tmp_path)
        cm.save_credential("user1", CredType.COOKIE, COOKIE_VALUES)
        cm.login("user1", CredType.COOKIE)
        cm.save_credential("user2", CredType.COOKIE, COOKIE2_VALUES)

        mock_client = MagicMock()
        mock_client.account.info.return_value = _make_account("user2", 99999)
        mock_create_client.return_value = mock_client

        parser, commands = build_parser(config=cfg, credential_manager=cm)
        args = parser.parse_args(["login", "switch", "user2"])
        commands["login"].execute(args)

        assert cm.current_user == "user2"

        out = capsys.readouterr().out
        assert "Switched to" in out
        assert "user2" in out

        cm = CredentialManager(cfg)
        parser, commands = build_parser(config=cfg, credential_manager=cm)
        args = parser.parse_args(["account"])
        commands["account"].execute(args)

        auth_arg = mock_create_client.call_args[0][0]
        assert isinstance(auth_arg, CookieAuth)
        assert auth_arg.get_cookies() == COOKIE2_VALUES

    @patch("cli115.cmds.base.create_client")
    def test_switch_validates_credentials_of_new_user(
        self, mock_create_client, tmp_path
    ):
        cm, config = _setup_cm(tmp_path)
        cm.save_credential("user1", CredType.COOKIE, COOKIE_VALUES)
        cm.login("user1", CredType.COOKIE)
        cm.save_credential("user2", CredType.COOKIE, COOKIE2_VALUES)

        mock_client = MagicMock()
        mock_client.account.info.return_value = _make_account("user2", 99999)
        mock_create_client.return_value = mock_client

        parser, commands = build_parser(config=config, credential_manager=cm)
        args = parser.parse_args(["login", "switch", "user2"])
        commands["login"].execute(args)

        # The client must have been created with user2's cookies
        auth_arg = mock_create_client.call_args[0][0]
        assert isinstance(auth_arg, CookieAuth)
        assert auth_arg.get_cookies() == COOKIE2_VALUES


class TestLogoutCommand:
    def test_logout_current_user_clears_session(self, tmp_path, capsys):
        cm, config = _setup_cm(tmp_path)
        cm.save_credential("testuser", CredType.COOKIE, COOKIE_VALUES)
        cm.login("testuser", CredType.COOKIE)

        parser, commands = build_parser(config=config, credential_manager=cm)
        args = parser.parse_args(["logout"])
        commands["logout"].execute(args)

        # Session must be cleared: _current_credential file removed
        assert not (tmp_path / CURRENT_CREDENTIAL_FILE).exists()

        out = capsys.readouterr().out
        assert "Logged out" in out
        assert "testuser" in out

    def test_logout_other_user_removes_credentials(self, tmp_path, capsys):
        cm, config = _setup_cm(tmp_path)
        cm.save_credential("user1", CredType.COOKIE, COOKIE_VALUES)
        cm.login("user1", CredType.COOKIE)
        cm.save_credential("user2", CredType.COOKIE, COOKIE2_VALUES)

        parser, commands = build_parser(config=config, credential_manager=cm)
        args = parser.parse_args(["logout", "user2"])
        commands["logout"].execute(args)

        # user2's credential file must be removed
        assert not (tmp_path / "user2.json").exists()
        # user1 must still be the current user
        assert cm.current_user == "user1"

        out = capsys.readouterr().out
        assert "Cleared" in out
        assert "user2" in out

    def test_logged_out_user_cannot_authenticate_on_next_call(self, tmp_path):
        cm, config = _setup_cm(tmp_path)
        cm.save_credential("testuser", CredType.COOKIE, COOKIE_VALUES)
        cm.login("testuser", CredType.COOKIE)

        parser, commands = build_parser(config=config, credential_manager=cm)
        args = parser.parse_args(["logout"])
        commands["logout"].execute(args)

        cm = CredentialManager(config)
        parser, commands = build_parser(config=config, credential_manager=cm)
        args = parser.parse_args(["account"])
        with pytest.raises(CredentialError):
            commands["account"].execute(args)
