"""CLI entry point for 115cli."""

import argparse
from collections import OrderedDict
from configparser import ConfigParser
from pathlib import Path
import sys

from cli115.__version__ import __version__
from cli115.client.webapi import DEFAULT_USER_AGENT
from cli115.credentials import CredentialManager
from cli115.cmds.account import AccountCommand
from cli115.cmds.auth import AuthCommand
from cli115.cmds.base import BaseCommand
from cli115.cmds.config import ConfigCommand
from cli115.cmds.cp import CpCommand
from cli115.cmds.download import DownloadCommand
from cli115.cmds.fetch import FetchCommand
from cli115.cmds.find import FindCommand
from cli115.cmds.id import IdCommand
from cli115.cmds.login import LoginCommand
from cli115.cmds.logout import LogoutCommand
from cli115.cmds.ls import LsCommand
from cli115.cmds.mkdir import MkdirCommand
from cli115.cmds.mv import MvCommand
from cli115.cmds.rm import RmCommand
from cli115.cmds.stat import StatCommand
from cli115.cmds.upload import UploadCommand
from cli115.cmds.url import UrlCommand
from cli115.exceptions import CommandLineError, CredentialError


COMMANDS = OrderedDict(
    [
        ("account", AccountCommand),
        ("auth", AuthCommand),
        ("login", LoginCommand),
        ("logout", LogoutCommand),
        ("config", ConfigCommand),
        ("ls", LsCommand),
        ("find", FindCommand),
        ("cp", CpCommand),
        ("mv", MvCommand),
        ("rm", RmCommand),
        ("mkdir", MkdirCommand),
        ("upload", UploadCommand),
        ("stat", StatCommand),
        ("id", IdCommand),
        ("fetch", FetchCommand),
        ("download", DownloadCommand),
        ("url", UrlCommand),
    ]
)

DEFAULT_CONFIG_DIR = Path.home() / ".115cli"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.ini"
DEFAULT_CREDENTIALS_DIR = DEFAULT_CONFIG_DIR / "credentials"


def load_config() -> ConfigParser:
    config = ConfigParser()
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


def build_parser(
    config: ConfigParser,
    credential_manager: CredentialManager,
) -> tuple[argparse.ArgumentParser, dict[str, BaseCommand]]:
    parser = argparse.ArgumentParser(
        prog="115cli", description="CLI tool for 115 netdisk"
    )
    parser.add_argument(
        "-V", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    commands = {}
    for name, cls in COMMANDS.items():
        cmd = cls(config=config, credential_manager=credential_manager)
        sub = subparsers.add_parser(name, help=cls.__doc__)
        cmd.register(sub)
        commands[name] = cmd

    return parser, commands


def _find_leaf_parser(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> argparse.ArgumentParser:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            chosen = getattr(args, action.dest, None)
            if chosen is not None and chosen in action.choices:
                return _find_leaf_parser(action.choices[chosen], args)
            break
    return parser


def main(argv: list[str] | None = None) -> None:
    config = load_config()
    cm = CredentialManager(config)
    parser, commands = build_parser(config=config, credential_manager=cm)

    # First pass: permissive parse so that unknown options don't silently
    # bubble up to the root parser and show the wrong usage message.
    args, unknown = parser.parse_known_args(argv)

    # Second pass: validate the remaining tokens against the innermost
    # subparser that was activated, so the error message and usage string
    # always refer to the right (sub)command.
    if unknown:
        leaf = _find_leaf_parser(parser, args)
        leaf.error(f"unrecognized arguments: {' '.join(unknown)}")

    cmd = commands.get(args.command)
    if cmd is None:
        parser.print_help()
        sys.exit(1)

    try:
        cmd.execute(args)
    except (CommandLineError, CredentialError, OSError) as e:
        typ = type(e).__name__
        if isinstance(e, CommandLineError):
            typ = "Error"
        print(f"{typ}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
