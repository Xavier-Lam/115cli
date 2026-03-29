import configparser
import json

import pytest

from cli115.credentials import CredentialManager, CredType, CURRENT_CREDENTIAL_FILE
from cli115.exceptions import CredentialError


COOKIE_VALUES = {"UID": "user1", "CID": "cid1", "SEID": "seid1", "KID": "kid1"}
COOKIE2_VALUES = {"UID": "u2", "CID": "c2", "SEID": "s2", "KID": "k2"}


def _make_cm(tmp_path):
    config = configparser.ConfigParser()
    config["general"] = {"credentials": str(tmp_path)}
    return CredentialManager(config)


class TestCurrentUser:
    def test_active_user(self, tmp_path):
        cm = _make_cm(tmp_path)
        (tmp_path / CURRENT_CREDENTIAL_FILE).write_text("user1")

        assert cm.current_user == "user1"

    def test_no_active_user(self, tmp_path):
        cm = _make_cm(tmp_path)

        with pytest.raises(CredentialError):
            _ = cm.current_user


class TestCurrentCredential:
    def test_active_user(self, tmp_path):
        cm = _make_cm(tmp_path)
        cm.save_credential("user1", CredType.COOKIE, COOKIE_VALUES)
        cm.login("user1", CredType.COOKIE)

        cred_type, data = cm.current_credential

        assert cred_type == CredType.COOKIE
        assert data == COOKIE_VALUES

    def test_no_active_user(self, tmp_path):
        cm = _make_cm(tmp_path)

        with pytest.raises(CredentialError):
            _ = cm.current_credential


class TestLogin:
    def test_login(self, tmp_path):
        cm = _make_cm(tmp_path)
        cm.save_credential("user1", CredType.COOKIE, COOKIE_VALUES)
        cm.save_credential("user2", CredType.COOKIE, COOKIE2_VALUES)
        cm.login("user1", CredType.COOKIE)
        assert cm.current_user == "user1"
        cm = _make_cm(tmp_path)
        assert cm.current_user == "user1"

        cm.login("user2", CredType.COOKIE)
        assert cm.current_user == "user2"
        cm = _make_cm(tmp_path)
        assert cm.current_user == "user2"

    def test_file_wrote(self, tmp_path):
        cm = _make_cm(tmp_path)
        cm.save_credential("user1", CredType.COOKIE, COOKIE_VALUES)
        cm.save_credential("user2", CredType.COOKIE, COOKIE2_VALUES)

        cm.login("user1", CredType.COOKIE)

        current_file = tmp_path / CURRENT_CREDENTIAL_FILE
        assert current_file.exists()
        assert current_file.read_text().strip() == "user1"
        cred_path = tmp_path / "user1.json"
        data = json.loads(cred_path.read_text())
        assert data["type"] == "cookie"

        cm.login("user2", CredType.COOKIE)
        assert current_file.read_text().strip() == "user2"
        cred_path = tmp_path / "user2.json"
        data = json.loads(cred_path.read_text())
        assert data["type"] == "cookie"


class TestLogout:
    def test_logout(self, tmp_path):
        cm = _make_cm(tmp_path)
        cm.save_credential("user1", CredType.COOKIE, COOKIE_VALUES)
        cm.login("user1", CredType.COOKIE)

        cm.logout()
        with pytest.raises(CredentialError):
            _ = cm.current_user
        with pytest.raises(CredentialError):
            _ = cm.current_credential
        cm = _make_cm(tmp_path)
        with pytest.raises(CredentialError):
            _ = cm.current_user
        with pytest.raises(CredentialError):
            _ = cm.current_credential

    def test_removes_current_user_file(self, tmp_path):
        cm = _make_cm(tmp_path)
        cm.save_credential("user1", CredType.COOKIE, COOKIE_VALUES)
        cm.login("user1", CredType.COOKIE)

        cm.logout()
        assert not (tmp_path / CURRENT_CREDENTIAL_FILE).exists()

    def test_no_error_if_not_logged_in(self, tmp_path):
        cm = _make_cm(tmp_path)
        # Should not raise even when no current user file exists
        cm.logout()


class TestGetCredential:
    def test_loads_stored_data(self, tmp_path):
        cm = _make_cm(tmp_path)
        cm.save_credential("user1", CredType.COOKIE, COOKIE_VALUES)

        cred_type, data = cm.get_credential("user1")

        assert cred_type == CredType.COOKIE
        assert data == COOKIE_VALUES

    def test_raises_if_user_not_found(self, tmp_path):
        cm = _make_cm(tmp_path)

        with pytest.raises(CredentialError, match="user1"):
            cm.get_credential("user1")


class TestSaveCredential:
    def test_creates_credential_file(self, tmp_path):
        cm = _make_cm(tmp_path)
        cm.save_credential("user1", CredType.COOKIE, COOKIE_VALUES)

        cred_file = tmp_path / "user1.json"
        assert cred_file.exists()
        data = json.loads(cred_file.read_text())
        assert data["uid"] == "user1"
        assert data["type"] == CredType.COOKIE
        assert data["cookie"] == COOKIE_VALUES

    def test_updates_existing_credential(self, tmp_path):
        cm = _make_cm(tmp_path)
        cm.save_credential("user1", CredType.COOKIE, COOKIE_VALUES)
        cm.save_credential("user1", CredType.COOKIE, COOKIE2_VALUES)

        data = json.loads((tmp_path / "user1.json").read_text())
        assert data["cookie"] == COOKIE2_VALUES

    def test_creates_credentials_dir_if_missing(self, tmp_path):
        sub_dir = tmp_path / "subdir"
        config = configparser.ConfigParser()
        config["general"] = {"credentials": str(sub_dir)}
        cm = CredentialManager(config)

        cm.save_credential("user1", CredType.COOKIE, COOKIE_VALUES)

        assert (sub_dir / "user1.json").exists()


class TestClearCredential:
    def test_removes_all(self, tmp_path):
        cm = _make_cm(tmp_path)
        cm.save_credential("user1", CredType.COOKIE, COOKIE_VALUES)

        cm.clear_credential("user1")

        assert not (tmp_path / "user1.json").exists()

    def test_removes_type(self, tmp_path):
        cm = _make_cm(tmp_path)
        cm.save_credential("user1", CredType.COOKIE, COOKIE_VALUES)

        cm.clear_credential("user1", CredType.COOKIE)

        cred_file = tmp_path / "user1.json"
        assert cred_file.exists()
        data = json.loads(cred_file.read_text())
        assert "cookie" not in data

    def test_raises_if_user_not_found(self, tmp_path):
        cm = _make_cm(tmp_path)

        with pytest.raises(FileNotFoundError, match="user1"):
            cm.clear_credential("user1")
