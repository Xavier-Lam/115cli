from __future__ import annotations

import hashlib
from http.cookies import SimpleCookie
import re
from typing import BinaryIO


def normalize_path(path: str) -> str:
    path = path.replace("\\", "/").strip()
    if not path or path == "/":
        return "/"
    if not path.startswith("/"):
        path = "/" + path
    return path.rstrip("/")


def parse_cookie_string(cookie_str: str) -> dict[str, str]:
    sc = SimpleCookie()
    sc.load(cookie_str)
    return {key: morsel.value for key, morsel in sc.items()}


_SIZE_UNITS: dict[str, int] = {
    "B": 1,
    "K": 1024,
    "KB": 1024,
    "M": 1024**2,
    "MB": 1024**2,
    "G": 1024**3,
    "GB": 1024**3,
    "T": 1024**4,
    "TB": 1024**4,
    "P": 1024**5,
    "PB": 1024**5,
}


def parse_size(s: str | int) -> int:
    """Convert a human-readable file size to bytes.

    Accepts an integer (returned as-is) or a string with an optional unit
    suffix such as ``"10MB"``, ``"1GB"``, ``"2M"``, ``"512KB"``, ``"1.5GB"``
    (case-insensitive).  A bare number string (e.g. ``"1048576"``) is treated
    as bytes.

    Raises ``ValueError`` for unrecognised formats.
    """
    if isinstance(s, int):
        return s
    s = s.strip()
    if re.fullmatch(r"[0-9]+", s):
        return int(s)
    m = re.fullmatch(r"([0-9]*\.?[0-9]+)\s*([A-Za-z]+)", s)
    if not m:
        raise ValueError(f"Invalid file size: {s!r}")
    number, unit = m.groups()
    unit = unit.upper()
    if unit not in _SIZE_UNITS:
        raise ValueError(f"Unknown unit {unit!r} in file size: {s!r}")
    return int(float(number) * _SIZE_UNITS[unit])


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
