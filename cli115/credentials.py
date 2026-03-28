"""Credential management for the CLI."""

from __future__ import annotations

from configparser import ConfigParser
import json
from enum import Enum
from pathlib import Path

from cli115.exceptions import CommandError


CURRENT_CREDENTIAL_FILE = "_current_credential"


class CredType(str, Enum):
    COOKIE = "cookie"

    def __str__(self) -> str:
        return self.value


class CredentialManager:
    """Manages reading and writing credentials on disk."""

    def __init__(self, config: ConfigParser) -> None:
        self.cfg = config

    @property
    def current_user(self) -> str:
        """Return ``uid`` for the active user.

        Raises ``FileNotFoundError`` if no user is currently logged in.
        """
        current_file = self.credentials_dir / CURRENT_CREDENTIAL_FILE
        if not current_file.exists():
            raise CommandError("No active user. Use '115cli login' to log in.")
        return current_file.read_text().strip()

    @property
    def current_credential(self) -> tuple[CredType, dict]:
        """Load credentials for the currently active user."""
        uid = self.current_user
        return self.get_credential(uid)

    def login(self, uid: str, cred_type: CredType | None = None) -> None:
        """Record which user and credential type are currently active."""
        cred_dir = self.credentials_dir
        cred_dir.mkdir(parents=True, exist_ok=True)
        (cred_dir / CURRENT_CREDENTIAL_FILE).write_text(uid)
        cred_path = cred_dir / f"{uid}.json"
        with open(cred_path, "r") as f:
            stored = json.load(f)
        if not cred_type:
            cred_type = _get_credential_type(stored, uid)
        stored["type"] = cred_type
        with open(cred_path, "w") as f:
            json.dump(stored, f, indent=2)

    def logout(self) -> None:
        """Clear the active user pointer without deleting stored credentials."""
        current_file = self.credentials_dir / CURRENT_CREDENTIAL_FILE
        if current_file.exists():
            current_file.unlink()

    def get_credential(
        self, uid: str, cred_type: CredType | None = None
    ) -> tuple[CredType, dict]:
        """Load credentials for *uid* from ``{uid}.json``."""
        cred_path = self.credentials_dir / f"{uid}.json"
        if not cred_path.exists():
            raise CommandError(f"No credentials found for user '{uid}'.")
        with open(cred_path) as f:
            credentials = json.load(f)
        if cred_type is None:
            cred_type = _get_credential_type(credentials, uid)
        elif cred_type not in credentials:
            raise CommandError(f"No '{cred_type}' credentials found for user '{uid}'.")
        return cred_type, credentials[cred_type]

    def save_credential(self, uid: str, cred_type: CredType, data: dict) -> None:
        """Save credentials for a user without updating the current user pointer."""
        cred_dir = self.credentials_dir
        cred_dir.mkdir(parents=True, exist_ok=True)
        cred_path = cred_dir / f"{uid}.json"
        stored: dict = {"uid": uid}
        if cred_path.exists():
            with open(cred_path) as f:
                try:
                    stored = json.load(f)
                except Exception:
                    pass
        if "type" not in stored:
            stored["type"] = cred_type
        stored[cred_type] = data
        with open(cred_path, "w") as f:
            json.dump(stored, f, indent=2)

    def clear_credential(self, uid: str, cred_type: CredType | None = None) -> None:
        """Remove stored credentials for a user."""
        cred_path = self.credentials_dir / f"{uid}.json"
        if not cred_path.exists():
            raise FileNotFoundError(f"No credentials found for user '{uid}'.")
        if cred_type is None:
            cred_path.unlink()
        else:
            with open(cred_path, "r") as f:
                stored = json.load(f)
            if stored.get("type") == cred_type:
                del stored["type"]
            if cred_type in stored:
                del stored[cred_type]
            with open(cred_path, "w") as f:
                json.dump(stored, f, indent=2)

    @property
    def credentials_dir(self) -> Path:
        return Path(self.cfg["general"]["credentials"])


def _get_credential_type(credentials: dict, uid: str) -> CredType:
    cred_type = credentials.get("type")
    if not cred_type:
        available = [t for t in CredType if t in credentials]
        if not available:
            raise CommandError(f"No credentials found for user '{uid}'.")
        cred_type = available[0]
    return cred_type
