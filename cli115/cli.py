"""CLI entry point for 115cli."""

import argparse
import sys

from cli115.cmds.base import BaseCommand
from cli115.cmds.account import AccountCommand
from cli115.cmds.auth import AuthCommand
from cli115.cmds.config_cmd import ConfigCommand
from cli115.cmds.cp import CpCommand
from cli115.cmds.download import DownloadCommand
from cli115.cmds.download_info import DownloadInfoCommand
from cli115.cmds.id import IdCommand
from cli115.cmds.info import InfoCommand
from cli115.cmds.find import FindCommand
from cli115.cmds.ls import LsCommand
from cli115.cmds.mkdir import MkdirCommand
from cli115.cmds.mv import MvCommand
from cli115.cmds.rm import RmCommand
from cli115.cmds.upload import UploadCommand

COMMANDS: dict[str, BaseCommand] = {
    "account": AccountCommand(),
    "auth": AuthCommand(),
    "config": ConfigCommand(),
    "ls": LsCommand(),
    "find": FindCommand(),
    "cp": CpCommand(),
    "mv": MvCommand(),
    "rm": RmCommand(),
    "mkdir": MkdirCommand(),
    "upload": UploadCommand(),
    "info": InfoCommand(),
    "id": IdCommand(),
    "download": DownloadCommand(),
    "download-info": DownloadInfoCommand(),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="115cli", description="CLI tool for 115 netdisk"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name, cmd in COMMANDS.items():
        sub = subparsers.add_parser(name, help=cmd.__class__.__doc__)
        cmd.register(sub)

    return parser


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
    parser = build_parser()

    # First pass: permissive parse so that unknown options don't silently
    # bubble up to the root parser and show the wrong usage message.
    args, unknown = parser.parse_known_args(argv)

    # Second pass: validate the remaining tokens against the innermost
    # subparser that was activated, so the error message and usage string
    # always refer to the right (sub)command.
    if unknown:
        leaf = _find_leaf_parser(parser, args)
        leaf.error(f"unrecognized arguments: {' '.join(unknown)}")

    cmd = COMMANDS.get(args.command)
    if cmd is None:
        parser.print_help()
        sys.exit(1)

    cmd.execute(args)


if __name__ == "__main__":
    main()
