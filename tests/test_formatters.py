import json

from cli115.cmds.formatter import (
    JsonListFormatter,
    JsonPairFormatter,
    PlainListFormatter,
    PlainPairFormatter,
    TableListFormatter,
)


class TestPlainPairFormatter:
    def setup_method(self):
        self.fmt = PlainPairFormatter()

    def test_single_pair(self):
        assert self.fmt.format([("Key", "Value")]) == "Key: Value"

    def test_multiple_pairs(self):
        assert self.fmt.format([("Name", "foo"), ("Size", 42)]) == "Name: foo\nSize: 42"

    def test_empty_pairs(self):
        assert self.fmt.format([]) == ""

    def test_none_value(self):
        assert self.fmt.format([("Path", None)]) == "Path: None"


class TestJsonPairFormatter:
    def setup_method(self):
        self.fmt = JsonPairFormatter()

    def test_produces_valid_json(self):
        data = json.loads(self.fmt.format([("name", "foo"), ("size", 42)]))
        assert data["name"] == "foo"
        assert data["size"] == 42

    def test_non_serializable_value_becomes_string(self):
        from datetime import datetime

        dt = datetime(2025, 1, 1, 12, 0, 0)
        data = json.loads(self.fmt.format([("created", dt)]))
        assert isinstance(data["created"], str)

    def test_nested_dict_preserved(self):
        data = json.loads(self.fmt.format([("cookies", {"UID": "u1", "CID": "c1"})]))
        assert data["cookies"]["UID"] == "u1"

    def test_empty_pairs(self):
        assert json.loads(self.fmt.format([])) == {}


class TestPlainListFormatter:
    def setup_method(self):
        self.fmt = PlainListFormatter()

    def test_single_record(self):
        result = self.fmt.format([[("Name", "file.txt"), ("Size", 100)]])
        assert "Name: file.txt" in result
        assert "Size: 100" in result

    def test_multiple_records_separated_by_blank_line(self):
        records = [
            [("Name", "a.txt")],
            [("Name", "b.txt")],
        ]
        result = self.fmt.format(records)
        lines = result.split("\n")
        assert "" in lines
        assert "  Name: a.txt" in result
        assert "  Name: b.txt" in result

    def test_no_trailing_blank_line(self):
        records = [[("A", "x")], [("A", "y")]]
        result = self.fmt.format(records)
        assert not result.endswith("\n\n")

    def test_empty_records(self):
        assert self.fmt.format([]) == "No entries found."


class TestJsonListFormatter:
    def setup_method(self):
        self.fmt = JsonListFormatter()

    def test_produces_valid_json_array(self):
        records = [[("name", "foo"), ("size", 1)], [("name", "bar"), ("size", 2)]]
        data = json.loads(self.fmt.format(records))
        assert isinstance(data, list)
        assert len(data) == 2

    def test_record_fields_correct(self):
        data = json.loads(self.fmt.format([[("hash", "abc"), ("status", "done")]]))
        assert data[0]["hash"] == "abc"
        assert data[0]["status"] == "done"

    def test_empty_records(self):
        assert json.loads(self.fmt.format([])) == []


class TestTableListFormatter:
    def setup_method(self):
        self.fmt = TableListFormatter()

    def test_returns_empty_for_no_records(self):
        assert self.fmt.format([]) == ""

    def test_header_row_present(self):
        result = self.fmt.format([[("Name", "file.txt"), ("Size", "1 KB")]])
        assert "Name" in result
        assert "Size" in result

    def test_data_row_present(self):
        result = self.fmt.format([[("Name", "file.txt"), ("Size", "1 KB")]])
        assert "file.txt" in result
        assert "1 KB" in result

    def test_separator_line_present(self):
        lines = self.fmt.format([[("A", "x"), ("B", "y")]]).split("\n")
        assert len(lines) == 3
        assert lines[1].startswith("-")

    def test_multiple_rows(self):
        records = [
            [("Name", "file1.txt"), ("Size", "1 KB")],
            [("Name", "file2.txt"), ("Size", "10 MB")],
        ]
        lines = self.fmt.format(records).split("\n")
        assert len(lines) == 4

    def test_column_width_matches_longest_value(self):
        records = [
            [("Name", "short"), ("Size", "1 KB")],
            [("Name", "a-very-long-name"), ("Size", "2 KB")],
        ]
        lines = self.fmt.format(records).split("\n")
        col_widths = [len(line) for line in lines]
        assert len(set(col_widths)) == 1
