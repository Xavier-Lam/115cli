import unittest

from cli115.helpers import normalize_path, parse_size


class TestNormalizePath(unittest.TestCase):

    def test_root(self):
        self.assertEqual(normalize_path("/"), "/")

    def test_empty_returns_root(self):
        self.assertEqual(normalize_path(""), "/")

    def test_strips_trailing_slash(self):
        self.assertEqual(normalize_path("/foo/bar/"), "/foo/bar")

    def test_adds_leading_slash(self):
        self.assertEqual(normalize_path("foo/bar"), "/foo/bar")

    def test_normalizes_backslashes(self):
        self.assertEqual(normalize_path("foo\\bar"), "/foo/bar")

    def test_strips_whitespace(self):
        self.assertEqual(normalize_path("  /foo  "), "/foo")


class TestParseSize(unittest.TestCase):
    def test_int_passthrough(self):
        self.assertEqual(parse_size(1024), 1024)

    def test_plain_integer_string(self):
        self.assertEqual(parse_size("1048576"), 1048576)

    def test_bytes_unit(self):
        self.assertEqual(parse_size("100B"), 100)

    def test_kilobytes(self):
        self.assertEqual(parse_size("512KB"), 512 * 1024)

    def test_k_suffix(self):
        self.assertEqual(parse_size("4K"), 4 * 1024)

    def test_megabytes(self):
        self.assertEqual(parse_size("10MB"), 10 * 1024 * 1024)

    def test_m_suffix(self):
        self.assertEqual(parse_size("2M"), 2 * 1024 * 1024)

    def test_gigabytes(self):
        self.assertEqual(parse_size("1GB"), 1024**3)

    def test_g_suffix(self):
        self.assertEqual(parse_size("1G"), 1024**3)

    def test_terabytes(self):
        self.assertEqual(parse_size("1TB"), 1024**4)

    def test_petabytes(self):
        self.assertEqual(parse_size("1PB"), 1024**5)

    def test_float_value(self):
        self.assertEqual(parse_size("1.5GB"), int(1.5 * 1024**3))

    def test_case_insensitive(self):
        self.assertEqual(parse_size("8mb"), 8 * 1024 * 1024)
        self.assertEqual(parse_size("8Mb"), 8 * 1024 * 1024)

    def test_whitespace_stripped(self):
        self.assertEqual(parse_size("  4MB  "), 4 * 1024 * 1024)

    def test_space_between_number_and_unit(self):
        self.assertEqual(parse_size("4 MB"), 4 * 1024 * 1024)

    def test_invalid_string_raises(self):
        with self.assertRaises(ValueError):
            parse_size("abc")

    def test_unknown_unit_raises(self):
        with self.assertRaises(ValueError):
            parse_size("10XB")


if __name__ == "__main__":
    unittest.main()
