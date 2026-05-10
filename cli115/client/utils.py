"""Shared helpers for the cli115 client implementations."""

from __future__ import annotations

from datetime import datetime
from typing import BinaryIO
from urllib.parse import urlparse
import uuid

import httpcore

from cli115.client.models import Directory, File


def parse_ts(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value))
    except (ValueError, TypeError, OSError):
        pass
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


def parse_labels(fl) -> list[str]:
    if not fl or not isinstance(fl, list):
        return []
    names: list[str] = []
    for item in fl:
        if isinstance(item, dict) and "name" in item:
            names.append(item["name"])
        elif isinstance(item, str):
            names.append(item)
    return names


def parse_item(item: dict) -> Directory | File:
    kwargs = {
        "id": str(item["fid"]) if "fid" in item else str(item["cid"]),
        "parent_id": str(item.get("cid" if "fid" in item else "pid", "")),
        "name": item.get("n", ""),
        "path": None,  # it is a attribute defined in our project
        "pickcode": item.get("pc", ""),
        "created_time": parse_ts(item.get("tp")),
        "modified_time": parse_ts(item.get("te") or item.get("t")),
        "open_time": parse_ts(item.get("to")),
        "labels": parse_labels(item.get("fl")),
    }
    if "fid" in item:
        kwargs.update(
            {
                "size": int(item.get("s", 0)),
                "sha1": item.get("sha", ""),
                "file_type": item.get("ico", ""),
                "starred": bool(item.get("sta")),
            }
        )
        klass = File
    else:
        kwargs.update(
            {
                "file_count": int(item.get("fc", 0)),
            }
        )
        klass = Directory
    return klass(**kwargs)


def create_multipart_request(
    url: str,
    *,
    data: dict[str, str],
    filename: str,
    file: BinaryIO,
) -> httpcore.Request:
    parsed = urlparse(url)
    boundary = uuid.uuid4().hex
    content = _iter_streaming_multipart_content(
        boundary=boundary,
        data=data,
        filename=filename,
        file=file,
    )
    return httpcore.Request(
        method="POST",
        url=url,
        headers={
            "Host": parsed.netloc,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Transfer-Encoding": "chunked",
        },
        content=content,
    )


def _iter_streaming_multipart_content(
    *,
    boundary: str,
    data: dict[str, str],
    filename: str,
    file: BinaryIO,
):
    boundary_bytes = boundary.encode("ascii")

    for key, value in data.items():
        yield b"--" + boundary_bytes + b"\r\n"
        yield f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8")
        yield str(value).encode("utf-8")
        yield b"\r\n"

    yield b"--" + boundary_bytes + b"\r\n"
    yield (
        (
            "Content-Disposition: form-data; " f'name="file"; filename="{filename}"\r\n'
        ).encode("utf-8")
    )
    yield b"Content-Type: application/octet-stream\r\n\r\n"

    while chunk := file.read(64 * 1024):
        yield chunk

    yield b"\r\n"
    yield b"--" + boundary_bytes + b"--\r\n"
