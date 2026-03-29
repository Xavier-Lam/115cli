from datetime import datetime

from cli115.client.base import Directory, File
from cli115.client.utils import (
    parse_item,
    parse_labels,
    parse_ts,
)


class TestParseTs:
    def test_returns_none_for_falsy(self):
        assert parse_ts(None) is None
        assert parse_ts(0) is None
        assert parse_ts("") is None

    def test_parses_integer_timestamp(self):
        ts = 1700000000
        result = parse_ts(ts)
        assert isinstance(result, datetime)
        assert result == datetime.fromtimestamp(ts)

    def test_parses_string_timestamp(self):
        assert isinstance(parse_ts("1700000000"), datetime)

    def test_parses_datetime_hm_format(self):
        result = parse_ts("2024-01-15 10:30")
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parses_datetime_hms_format(self):
        result = parse_ts("2024-01-15 10:30:45")
        assert isinstance(result, datetime)
        assert result.second == 45

    def test_returns_none_for_invalid_string(self):
        assert parse_ts("not-a-date") is None


class TestParseLabels:
    def test_returns_empty_for_none(self):
        assert parse_labels(None) == []

    def test_returns_empty_for_empty_list(self):
        assert parse_labels([]) == []

    def test_returns_empty_for_non_list(self):
        assert parse_labels("string") == []

    def test_parses_dict_items(self):
        fl = [{"name": "label1"}, {"name": "label2"}]
        assert parse_labels(fl) == ["label1", "label2"]

    def test_parses_string_items(self):
        assert parse_labels(["tag1", "tag2"]) == ["tag1", "tag2"]

    def test_skips_dicts_without_name_key(self):
        fl = [{"other": "val"}, {"name": "ok"}]
        assert parse_labels(fl) == ["ok"]


class TestParseItem:
    def _file_raw(self, **overrides):
        base = {
            "fid": "111",
            "cid": "222",
            "n": "test.txt",
            "pc": "abc123",
            "s": 1024,
            "sha": "aabbcc",
            "ico": "txt",
            "sta": 0,
            "tp": 1700000000,
            "te": 1700001000,
        }
        base.update(overrides)
        return base

    def _dir_raw(self, **overrides):
        base = {
            "cid": "333",
            "pid": "0",
            "n": "myfolder",
            "pc": "def456",
            "fc": 5,
            "tp": 1700000000,
        }
        base.update(overrides)
        return base

    def test_parses_file(self):
        item = parse_item(self._file_raw())
        assert isinstance(item, File)
        assert not item.is_directory
        assert item.id == "111"
        assert item.parent_id == "222"
        assert item.name == "test.txt"
        assert item.size == 1024
        assert item.sha1 == "aabbcc"
        assert item.file_type == "txt"
        assert not item.starred

    def test_parses_directory(self):
        item = parse_item(self._dir_raw())
        assert isinstance(item, Directory)
        assert item.is_directory
        assert item.id == "333"
        assert item.parent_id == "0"
        assert item.name == "myfolder"
        assert item.file_count == 5

    def test_file_starred(self):
        item = parse_item(self._file_raw(sta=1))
        assert item.starred

    def test_file_labels(self):
        item = parse_item(self._file_raw(fl=[{"name": "fav"}]))
        assert item.labels == ["fav"]
