"""Configuration and credential management for the CLI."""

import configparser
import json
from pathlib import Path

from cli115.client.webapi import DEFAULT_USER_AGENT


DEFAULT_CONFIG_DIR = Path.home() / ".115cli"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.ini"
DEFAULT_CREDENTIALS_DIR = DEFAULT_CONFIG_DIR / "credentials"
CURRENT_CREDENTIAL_FILE = "_current_credential"


def get_config_dir() -> Path:
    return DEFAULT_CONFIG_DIR


def load_config() -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    config_file = DEFAULT_CONFIG_FILE
    if config_file.exists():
        config.read(config_file)
    if "general" not in config:
        config["general"] = {}
    if "credentials" not in config["general"]:
        config["general"]["credentials"] = str(DEFAULT_CREDENTIALS_DIR)
    if "user_agent" not in config["general"]:
        config["general"]["user_agent"] = DEFAULT_USER_AGENT
    if "download" not in config:
        config["download"] = {}
    if "min_split_size" not in config["download"]:
        config["download"]["min_split_size"] = "2M"
    if "max_connection" not in config["download"]:
        config["download"]["max_connection"] = "2"
    return config


def save_config(config: configparser.ConfigParser) -> None:
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    with open(DEFAULT_CONFIG_FILE, "w") as f:
        config.write(f)


def get_credentials_dir(config: configparser.ConfigParser | None = None) -> Path:
    if config is None:
        config = load_config()
    return Path(config["general"]["credentials"])


def save_cookie_credential(uid: str, cookies: dict[str, str]) -> Path:
    config = load_config()
    cred_dir = get_credentials_dir(config)
    cred_dir.mkdir(parents=True, exist_ok=True)

    filename = f"cookie_{uid}.json"
    cred_path = cred_dir / filename
    with open(cred_path, "w") as f:
        json.dump({"type": "cookie", "uid": uid, "cookies": cookies}, f, indent=2)

    # Update current credential pointer
    current_file = cred_dir / CURRENT_CREDENTIAL_FILE
    current_file.write_text(filename)

    # Ensure config is saved
    save_config(config)

    return cred_path


def load_current_credential() -> dict:
    config = load_config()
    cred_dir = get_credentials_dir(config)
    current_file = cred_dir / CURRENT_CREDENTIAL_FILE

    if not current_file.exists():
        raise FileNotFoundError(
            "No active credential found. Use '115cli auth cookie' to log in."
        )

    cred_filename = current_file.read_text().strip()
    cred_path = cred_dir / cred_filename

    if not cred_path.exists():
        raise FileNotFoundError(
            f"Credential file '{cred_filename}' not found. "
            "Use '115cli auth cookie' to log in."
        )

    with open(cred_path) as f:
        return json.load(f)


def get_user_agent(config: configparser.ConfigParser | None = None) -> str:
    """Return the configured User-Agent string."""
    if config is None:
        config = load_config()
    return config["general"]["user_agent"]
