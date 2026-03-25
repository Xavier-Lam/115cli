"""Fetch command – download a file from 115.com to local disk."""

from __future__ import annotations

import argparse
import os
import sys

from tqdm import tqdm

from cli115.client.utils import sha1_file
from cli115.cmds.base import BaseCommand


class FetchCommand(BaseCommand):
    """Download a file to local disk with progress."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("path", help="Remote file path on 115")
        parser.add_argument(
            "--check-integrity",
            action="store_true",
            help="Validate file integrity after download",
        )
        parser.add_argument(
            "-o",
            "--output",
            default=None,
            help="Local output path (default: current dir with remote filename)",
        )

    def execute(self, args: argparse.Namespace) -> None:
        client = self._create_client()
        info = client.file.info(args.path)
        output = args.output
        if not output:
            output = info.name
        elif os.path.isdir(output):
            output = os.path.join(output, info.name)
        bar = tqdm(
            total=info.size,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
        )
        with (
            client.file.fetch(args.path) as remote,
            open(output, "w+b") as f,
        ):
            while True:
                chunk = remote.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                bar.update(len(chunk))
                if bar.n >= info.size:
                    bar.close()

            if args.check_integrity:
                print("Checking file integrity...")
                sha1, size = sha1_file(f)
                if size != info.size:
                    raise ValueError(f"Size mismatch: expected {info.size}, got {size}")
                if sha1 != info.sha1:
                    raise ValueError(f"SHA1 mismatch: expected {info.sha1}, got {sha1}")

        print(f"Saved to {output}")
