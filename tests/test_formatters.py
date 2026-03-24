import json
import unittest

from cli115.cmds.formatter import (
    JsonListFormatter,
    JsonPairFormatter,
    PlainListFormatter,
    PlainPairFormatter,
    TableListFormatter,
)


# ---------------------------------------------------------------------------
# PlainPairFormatter
# ---------------------------------------------------------------------------


class TestPlainPairFormatter(unittest.TestCase):
    def setUp(self):
        self.fmt = PlainPairFormatter()

    def test_single_pair(self):
        result = self.fmt.format([("Key", "Value")])
        self.assertEqual(result, "Key: Value")

    def test_multiple_pairs(self):
        result = self.fmt.format([("Name", "foo"), ("Size", 42)])
        self.assertEqual(result, "Name: foo\nSize: 42")

    def test_empty_pairs(self):
        result = self.fmt.format([])
        self.assertEqual(result, "")

    def test_none_value(self):
        result = self.fmt.format([("Path", None)])
        self.assertEqual(result, "Path: None")


# ---------------------------------------------------------------------------
# JsonPairFormatter
# ---------------------------------------------------------------------------


class TestJsonPairFormatter(unittest.TestCase):
    def setUp(self):
        self.fmt = JsonPairFormatter()

    def test_produces_valid_json(self):
        result = self.fmt.format([("name", "foo"), ("size", 42)])
        data = json.loads(result)
        self.assertEqual(data["name"], "foo")
        self.assertEqual(data["size"], 42)

    def test_non_serializable_value_becomes_string(self):
        from datetime import datetime

        dt = datetime(2025, 1, 1, 12, 0, 0)
        result = self.fmt.format([("created", dt)])
        data = json.loads(result)
        self.assertIsInstance(data["created"], str)

    def test_nested_dict_preserved(self):
        result = self.fmt.format([("cookies", {"UID": "u1", "CID": "c1"})])
        data = json.loads(result)
        self.assertEqual(data["cookies"]["UID"], "u1")

    def test_empty_pairs(self):
        result = self.fmt.format([])
        self.assertEqual(json.loads(result), {})


# ---------------------------------------------------------------------------
# PlainListFormatter
# ---------------------------------------------------------------------------


class TestPlainListFormatter(unittest.TestCase):
    def setUp(self):
        self.fmt = PlainListFormatter()

    def test_single_record(self):
        records = [[("Name", "file.txt"), ("Size", 100)]]
        result = self.fmt.format(records)
        self.assertIn("Name: file.txt", result)
        self.assertIn("Size: 100", result)

    def test_multiple_records_separated_by_blank_line(self):
        records = [
            [("Name", "a.txt")],
            [("Name", "b.txt")],
        ]
        result = self.fmt.format(records)
        lines = result.split("\n")
        # Should have a blank line between records
        self.assertIn("", lines)
        self.assertIn("  Name: a.txt", result)
        self.assertIn("  Name: b.txt", result)

    def test_no_trailing_blank_line(self):
        records = [[("A", "x")], [("A", "y")]]
        result = self.fmt.format(records)
        self.assertFalse(result.endswith("\n\n"))

    def test_empty_records(self):
        result = self.fmt.format([])
        self.assertEqual(result, "No entries found.")


# ---------------------------------------------------------------------------
# JsonListFormatter
# ---------------------------------------------------------------------------


class TestJsonListFormatter(unittest.TestCase):
    def setUp(self):
        self.fmt = JsonListFormatter()

    def test_produces_valid_json_array(self):
        records = [[("name", "foo"), ("size", 1)], [("name", "bar"), ("size", 2)]]
        result = self.fmt.format(records)
        data = json.loads(result)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)

    def test_record_fields_correct(self):
        records = [[("hash", "abc"), ("status", "done")]]
        data = json.loads(self.fmt.format(records))
        self.assertEqual(data[0]["hash"], "abc")
        self.assertEqual(data[0]["status"], "done")

    def test_empty_records(self):
        data = json.loads(self.fmt.format([]))
        self.assertEqual(data, [])


# ---------------------------------------------------------------------------
# TableListFormatter
# ---------------------------------------------------------------------------


class TestTableListFormatter(unittest.TestCase):
    def setUp(self):
        self.fmt = TableListFormatter()

    def test_returns_empty_for_no_records(self):
        self.assertEqual(self.fmt.format([]), "")

    def test_header_row_present(self):
        records = [[("Name", "file.txt"), ("Size", "1 KB")]]
        result = self.fmt.format(records)
        self.assertIn("Name", result)
        self.assertIn("Size", result)

    def test_data_row_present(self):
        records = [[("Name", "file.txt"), ("Size", "1 KB")]]
        result = self.fmt.format(records)
        self.assertIn("file.txt", result)
        self.assertIn("1 KB", result)

    def test_separator_line_present(self):
        records = [[("A", "x"), ("B", "y")]]
        lines = self.fmt.format(records).split("\n")
        # 3 lines: header, separator, data
        self.assertEqual(len(lines), 3)
        self.assertRegex(lines[1], r"^-+")

    def test_multiple_rows(self):
        records = [
            [("Name", "file1.txt"), ("Size", "1 KB")],
            [("Name", "file2.txt"), ("Size", "10 MB")],
        ]
        lines = self.fmt.format(records).split("\n")
        # header + separator + 2 data rows = 4
        self.assertEqual(len(lines), 4)

    def test_column_width_matches_longest_value(self):
        records = [
            [("Name", "short"), ("Size", "1 KB")],
            [("Name", "a-very-long-name"), ("Size", "2 KB")],
        ]
        result = self.fmt.format(records)
        # All "Name" column cells should be padded to the same width
        lines = result.split("\n")
        col_widths = [len(line) for line in lines]
        # All rows should have the same total width
        self.assertEqual(len(set(col_widths)), 1)


if __name__ == "__main__":
    unittest.main()
