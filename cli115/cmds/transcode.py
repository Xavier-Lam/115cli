"""Stream command – starts a local HLS proxy for 115 video streams."""

from __future__ import annotations

import argparse

from cli115.client import Client, File
from cli115.cmds.base import BaseCommand
from cli115.exceptions import CommandLineError


class TranscodeCommand(BaseCommand):
    """Transcode a video file on 115 to make it available for streaming."""

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
        parser.add_argument("path", nargs="?", help="Remote file path on 115")
        parser.add_argument(
            "--id",
            dest="file_id",
            default=None,
            help="Stream by remote file ID instead of path",
        )

    def execute(self, args: argparse.Namespace) -> None:
        client = self._create_client()
        entry = self._get_entry(args, client)
        if self._is_available(client, entry):
            print("video is already available for streaming")
        else:
            self._transcode(client, entry)

    def _get_entry(self, args: argparse.Namespace, client: Client) -> File:
        if not args.file_id and not args.path:
            raise CommandLineError("either 'path' or '--id' is required")
        if args.file_id and args.path:
            raise CommandLineError("use either 'path' or '--id', not both")

        if args.path:
            entry = client.file.stat(args.path)
        else:
            entry = client.file.id(args.file_id)

        if entry.is_directory:
            raise CommandLineError(f"path is a directory: {entry.path or entry.id}")
        return entry

    def _is_available(self, client: Client, entry: File) -> bool:
        video_info = client.stream.info(entry)
        if "video_url" in video_info:
            return True

        if "queue_url" not in video_info:
            raise CommandLineError(
                "video stream is not available, check if the file is a valid video"
            )

        return False

    def _transcode(self, client: Client, entry: File):
        resp = client.stream.transcode_status(entry)
        print(f"videos in queue before this one: {resp['count']}")
        print(f"estimated time remaining: {int(resp['time']/60)}m")

        status = resp["status"]
        if status == 3:
            print("acceleration is already active")
        elif status not in (2, 4):  # not transcoding or already accelerated
            account = client.account.info()
            if account.vip:
                client.stream.accelerate_transcode(entry)
                print("VIP acceleration applied")
