"""Output formatters for CLI commands."""

from __future__ import annotations

import argparse
import json
from abc import ABC, abstractmethod
from enum import Enum

from cli115.client import FileSystemEntry


class PairFormat(str, Enum):
    PLAIN = "plain"
    JSON = "json"


class ListFormat(str, Enum):
    PLAIN = "plain"
    JSON = "json"
    TABLE = "table"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def format_entry(entry: FileSystemEntry) -> list[tuple[str, object]]:
    """Build a canonical list of key-value pairs for any ``FileSystemEntry``."""
    from cli115.client.base import Directory, File

    pairs: list[tuple[str, object]] = [
        ("Name", entry.name),
        ("ID", entry.id),
        ("Parent ID", entry.parent_id),
        ("Path", entry.path),
        ("Type", "Directory" if entry.is_directory else "File"),
        ("Pickcode", entry.pickcode),
    ]
    if isinstance(entry, File):
        pairs += [
            ("Size", entry.size),
            ("SHA1", entry.sha1),
            ("File Type", entry.file_type),
            ("Starred", entry.starred),
        ]
    elif isinstance(entry, Directory):
        pairs.append(("File Count", entry.file_count))
    if entry.created_time:
        pairs.append(("Created", entry.created_time))
    if entry.modified_time:
        pairs.append(("Modified", entry.modified_time))
    if entry.labels:
        pairs.append(("Labels", ", ".join(entry.labels)))
    return pairs


# ---------------------------------------------------------------------------
# Pair formatters – format a single set of key-value pairs
# ---------------------------------------------------------------------------


class PairFormatter(ABC):
    """Base class for formatting a list of key-value pairs."""

    @abstractmethod
    def format(self, pairs: list[tuple[str, object]]) -> str: ...


class PlainPairFormatter(PairFormatter):
    def format(self, pairs: list[tuple[str, object]]) -> str:
        return "\n".join(f"{key}: {value}" for key, value in pairs)


class JsonPairFormatter(PairFormatter):
    def format(self, pairs: list[tuple[str, object]]) -> str:
        return json.dumps(dict(pairs), indent=2, default=str)


# ---------------------------------------------------------------------------
# List formatters – format a list of records (each record is a list of pairs)
# ---------------------------------------------------------------------------


class ListFormatter(ABC):
    """Base class for formatting a list of records."""

    @abstractmethod
    def format(self, records: list[list[tuple[str, object]]]) -> str: ...


class PlainListFormatter(ListFormatter):
    def format(self, records: list[list[tuple[str, object]]]) -> str:
        if not records:
            return "No entries found."
        lines: list[str] = []
        for i, record in enumerate(records):
            for key, value in record:
                lines.append(f"  {key}: {value}")
            if i < len(records) - 1:
                lines.append("")
        return "\n".join(lines)


class JsonListFormatter(ListFormatter):
    def format(self, records: list[list[tuple[str, object]]]) -> str:
        data = [dict(record) for record in records]
        return json.dumps(data, indent=2, default=str, ensure_ascii=False)


class TableListFormatter(ListFormatter):
    def format(self, records: list[list[tuple[str, object]]]) -> str:
        if not records:
            return ""
        headers = [key for key, _ in records[0]]
        rows = [[str(value) for _, value in record] for record in records]
        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(widths):
                    widths[i] = max(widths[i], len(cell))
        header_line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
        separator = "  ".join("-" * w for w in widths)
        row_lines = [
            "  ".join(cell.ljust(w) for cell, w in zip(row, widths)) for row in rows
        ]
        return "\n".join([header_line, separator] + row_lines)


# ---------------------------------------------------------------------------
# Formatter mixins – inherit to add --format support to a command
# ---------------------------------------------------------------------------


class FormatterMixin(ABC):
    def get_formatters(self) -> dict[str, type[PairFormatter | ListFormatter]]:
        return {}

    def get_formatter(
        self, name: str, args: argparse.Namespace
    ) -> PairFormatter | ListFormatter:
        formatters = self.get_formatters()
        formatter_cls = formatters.get(name)
        return formatter_cls()

    def register(self, parser: argparse.ArgumentParser) -> None:
        super().register(parser)
        self.add_format_argument(parser)

    def add_format_argument(self, parser: argparse.ArgumentParser) -> None:
        """Register ``--format`` on *parser* with the supported choices."""
        formatters = self.get_formatters()
        choices = list(formatters.keys())
        parser.add_argument(
            "--format",
            choices=choices,
            default=choices[0],
            help=f"Output format (default: {choices[0]})",
        )

    def output(self, pairs: list[tuple[str, object]], args: argparse.Namespace) -> None:
        """Print *pairs* formatted according to ``args.format``."""
        formatter = self.get_formatter(args.format, args)
        print(formatter.format(pairs))


class PairFormatterMixin(FormatterMixin):
    def get_formatters(self) -> dict[str, type[PairFormatter]]:
        return {
            PairFormat.PLAIN.value: PlainPairFormatter,
            PairFormat.JSON.value: JsonPairFormatter,
        }


class ListFormatterMixin(FormatterMixin):
    def get_formatters(self) -> dict[str, type[ListFormatter]]:
        return {
            ListFormat.TABLE.value: TableListFormatter,
            ListFormat.PLAIN.value: PlainListFormatter,
            ListFormat.JSON.value: JsonListFormatter,
        }
