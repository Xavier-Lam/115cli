import unittest
from datetime import datetime

from cli115.client.base import Directory, File
from cli115.client.utils import (
    parse_item,
    parse_labels,
    parse_ts,
)


class TestParseTs(unittest.TestCase):

    def test_returns_none_for_falsy(self):
        self.assertIsNone(parse_ts(None))
        self.assertIsNone(parse_ts(0))
        self.assertIsNone(parse_ts(""))

    def test_parses_integer_timestamp(self):
        ts = 1700000000
        result = parse_ts(ts)
        self.assertIsInstance(result, datetime)
        self.assertEqual(result, datetime.fromtimestamp(ts))

    def test_parses_string_timestamp(self):
        result = parse_ts("1700000000")
        self.assertIsInstance(result, datetime)

    def test_parses_datetime_hm_format(self):
        result = parse_ts("2024-01-15 10:30")
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 1)
        self.assertEqual(result.day, 15)

    def test_parses_datetime_hms_format(self):
        result = parse_ts("2024-01-15 10:30:45")
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.second, 45)

    def test_returns_none_for_invalid_string(self):
        result = parse_ts("not-a-date")
        self.assertIsNone(result)


class TestParseLabels(unittest.TestCase):

    def test_returns_empty_for_none(self):
        self.assertEqual(parse_labels(None), [])

    def test_returns_empty_for_empty_list(self):
        self.assertEqual(parse_labels([]), [])

    def test_returns_empty_for_non_list(self):
        self.assertEqual(parse_labels("string"), [])

    def test_parses_dict_items(self):
        fl = [{"name": "label1"}, {"name": "label2"}]
        self.assertEqual(parse_labels(fl), ["label1", "label2"])

    def test_parses_string_items(self):
        fl = ["tag1", "tag2"]
        self.assertEqual(parse_labels(fl), ["tag1", "tag2"])

    def test_skips_dicts_without_name_key(self):
        fl = [{"other": "val"}, {"name": "ok"}]
        self.assertEqual(parse_labels(fl), ["ok"])


class TestParseItem(unittest.TestCase):

    def _file_raw(self, **overrides):
        base = {
            "fid": "111",
            "cid": "222",  # parent folder id for files
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
            "cid": "333",  # directory's own id
            "pid": "0",  # parent id
            "n": "myfolder",
            "pc": "def456",
            "fc": 5,
            "tp": 1700000000,
        }
        base.update(overrides)
        return base

    def test_parses_file(self):
        item = parse_item(self._file_raw())
        self.assertIsInstance(item, File)
        self.assertFalse(item.is_directory)
        self.assertEqual(item.id, "111")
        self.assertEqual(item.parent_id, "222")
        self.assertEqual(item.name, "test.txt")
        self.assertEqual(item.size, 1024)
        self.assertEqual(item.sha1, "aabbcc")
        self.assertEqual(item.file_type, "txt")
        self.assertFalse(item.starred)

    def test_parses_directory(self):
        item = parse_item(self._dir_raw())
        self.assertIsInstance(item, Directory)
        self.assertTrue(item.is_directory)
        self.assertEqual(item.id, "333")
        self.assertEqual(item.parent_id, "0")
        self.assertEqual(item.name, "myfolder")
        self.assertEqual(item.file_count, 5)

    def test_file_starred(self):
        item = parse_item(self._file_raw(sta=1))
        self.assertTrue(item.starred)

    def test_file_labels(self):
        item = parse_item(self._file_raw(fl=[{"name": "fav"}]))
        self.assertEqual(item.labels, ["fav"])


if __name__ == "__main__":
    unittest.main()
