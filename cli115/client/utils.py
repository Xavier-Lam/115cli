"""Shared helpers for the cli115 client implementations."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import BinaryIO

from cli115.client.base import Directory, File
from cli115.exceptions import (
    APIError,
    AlreadyExistsError,
    NotFoundError,
)


def check_response(resp: dict) -> dict:
    state = resp.get("state")
    if state is True or state == 1:
        return resp
    errno = resp.get("errno") or resp.get("errNo") or resp.get("code") or 0
    message = (
        resp.get("error")
        or resp.get("message")
        or resp.get("msg")
        or "Unknown API error"
    )
    if errno == 990002 or errno == 20018:
        raise NotFoundError(message, errno=errno)
    if errno == 20004:
        raise AlreadyExistsError(message, errno=errno)
    raise APIError(message, errno=errno)


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


def normalize_path(path: str) -> str:
    path = path.replace("\\", "/").strip()
    if not path or path == "/":
        return "/"
    if not path.startswith("/"):
        path = "/" + path
    return path.rstrip("/")


_CHUNK_SIZE = 8 * 1024 * 1024  # 8 MiB


def sha1_file(file: BinaryIO) -> tuple[str, int]:
    file.seek(0)
    try:
        h = hashlib.sha1()
        size = 0
        while True:
            chunk = file.read(_CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
            size += len(chunk)
        return h.hexdigest().upper(), size
    finally:
        file.seek(0)
