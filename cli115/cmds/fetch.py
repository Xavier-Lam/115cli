"""Fetch command – download a file from 115.com to local disk."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import os
import time

from tqdm import tqdm

from cli115.cmds.base import BaseCommand
from cli115.helpers import parse_size, sha1_file


class FetchCommand(BaseCommand):
    """Download a file to local disk with progress."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("path", help="Remote file path on 115")
        parser.add_argument(
            "--chunk-size",
            type=parse_size,
            default="8MB",
            help="Chunk size for downloading (default: 8MB, e.g. '4MB', '1048576')",
        )
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
        info = client.file.stat(args.path)
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
        start = time.monotonic()
        with (
            client.file.open(args.path) as remote,
            open(output, "w+b") as f,
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            remote.set_stream(True)
            write_future = None
            while True:
                chunk = remote.read(args.chunk_size)
                if write_future is not None:
                    write_future.result()
                if not chunk:
                    break
                bar.update(len(chunk))
                if bar.n >= info.size:
                    bar.close()
                write_future = pool.submit(f.write, chunk)
            if write_future is not None:
                write_future.result()

            download_elapsed = time.monotonic() - start
            print(f"Download time: {_format_duration(download_elapsed)}")

            if args.check_integrity:
                print("Checking file integrity...")
                sha1, size = sha1_file(f)
                if size != info.size:
                    raise ValueError(f"Size mismatch: expected {info.size}, got {size}")
                if sha1 != info.sha1:
                    raise ValueError(f"SHA1 mismatch: expected {info.sha1}, got {sha1}")

        print(f"Saved to {output}")


def _format_duration(total_seconds: float) -> str:
    secs = int(total_seconds)
    ms = int((total_seconds - secs) * 1000)
    hours, rem = divmod(secs, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    if minutes:
        return f"{minutes}:{seconds:02d}"
    if ms:
        return f"{seconds}.{ms:03d} seconds"
    return f"{seconds} seconds"
