import pytest

from cli115.helpers import join_path, normalize_path, parse_cookie_string, parse_size


class TestJoinPath:
    def test_simple_join(self):
        assert join_path("/remote/dir", "file.txt") == "/remote/dir/file.txt"

    def test_trailing_slash_on_base_stripped(self):
        assert join_path("/remote/dir/", "file.txt") == "/remote/dir/file.txt"

    def test_multiple_parts(self):
        assert join_path("/base", "sub", "file.bin") == "/base/sub/file.bin"

    def test_single_segment_base(self):
        assert join_path("/dir", "name.txt") == "/dir/name.txt"

    def test_no_double_slash(self):
        assert "//" not in join_path("/base/", "/child")

    def test_root_base(self):
        assert join_path("/", "dir") == "/dir"


class TestNormalizePath:
    def test_root(self):
        assert normalize_path("/") == "/"

    def test_empty_returns_root(self):
        assert normalize_path("") == "/"

    def test_strips_trailing_slash(self):
        assert normalize_path("/foo/bar/") == "/foo/bar"

    def test_adds_leading_slash(self):
        assert normalize_path("foo/bar") == "/foo/bar"

    def test_normalizes_backslashes(self):
        assert normalize_path("foo\\bar") == "/foo/bar"

    def test_strips_whitespace(self):
        assert normalize_path("  /foo  ") == "/foo"


class TestParseCookieString:
    def test_standard(self):
        cookie = "UID=u1; CID=c1; SEID=s1; KID=k1"
        result = parse_cookie_string(cookie)
        assert result["UID"] == "u1"
        assert result["CID"] == "c1"
        assert result["SEID"] == "s1"
        assert result["KID"] == "k1"

    def test_extra_values(self):
        cookie = "UID=u1; CID=c1; SEID=s1; KID=k1; OTHER=x"
        result = parse_cookie_string(cookie)
        assert len(result) == 5
        assert result["OTHER"] == "x"


class TestParseSize:
    def test_int_passthrough(self):
        assert parse_size(1024) == 1024

    def test_plain_integer_string(self):
        assert parse_size("1048576") == 1048576

    def test_bytes_unit(self):
        assert parse_size("100B") == 100

    def test_kilobytes(self):
        assert parse_size("512KB") == 512 * 1024

    def test_k_suffix(self):
        assert parse_size("4K") == 4 * 1024

    def test_megabytes(self):
        assert parse_size("10MB") == 10 * 1024 * 1024

    def test_m_suffix(self):
        assert parse_size("2M") == 2 * 1024 * 1024

    def test_gigabytes(self):
        assert parse_size("1GB") == 1024**3

    def test_g_suffix(self):
        assert parse_size("1G") == 1024**3

    def test_terabytes(self):
        assert parse_size("1TB") == 1024**4

    def test_petabytes(self):
        assert parse_size("1PB") == 1024**5

    def test_float_value(self):
        assert parse_size("1.5GB") == int(1.5 * 1024**3)

    def test_case_insensitive(self):
        assert parse_size("8mb") == 8 * 1024 * 1024
        assert parse_size("8Mb") == 8 * 1024 * 1024

    def test_whitespace_stripped(self):
        assert parse_size("  4MB  ") == 4 * 1024 * 1024

    def test_space_between_number_and_unit(self):
        assert parse_size("4 MB") == 4 * 1024 * 1024

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError):
            parse_size("abc")

    def test_unknown_unit_raises(self):
        with pytest.raises(ValueError):
            parse_size("10XB")
