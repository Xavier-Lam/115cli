from unittest.mock import MagicMock

import pytest

from cli115.client.lazy import LazyCollection, LazyPathCollection, LazyPathMixin
from cli115.client.models import Pagination


def _make_fetch(items, total):
    def fetch(page, page_size):
        offset = (page - 1) * page_size
        limit = min(page_size, total - offset)
        pg = Pagination(total=total, offset=offset, limit=len(items))
        return items[:limit], pg

    return fetch


class _SimpleEntry(LazyPathMixin):
    def __init__(self, name, parent_id, id, file_client=None):
        self.name = name
        self.parent_id = parent_id
        self.id = id
        self._file_client = file_client


class TestLazyPathMixin:
    def test_lazypath_recursive_load(self):
        mock_client = MagicMock()

        class Dir:
            def __init__(self, name, parent_id):
                self.name = name
                self.parent_id = parent_id

        def id_side_effect(id):
            if id == "p2":
                return Dir("grand", "p1")
            if id == "p1":
                return Dir("parent", "0")
            raise KeyError(id)

        mock_client.id.side_effect = id_side_effect
        entry = _SimpleEntry("file.txt", "p2", "f1", file_client=mock_client)

        path = entry.path
        assert path == "/parent/grand/file.txt"
        assert mock_client.id.call_count == 2
        assert [c.args[0] for c in mock_client.id.call_args_list] == ["p2", "p1"]

        mock_client.id.reset_mock()
        _ = entry.path
        mock_client.id.assert_not_called()


class TestLazyCollection:
    def test_len(self):
        col = LazyCollection(_make_fetch([1, 2, 3], 3), page_size=10)
        assert len(col) == 3
        col = LazyCollection(_make_fetch([1, 2, 3], 50), page_size=3)
        assert len(col) == 50

    def test_getitem(self):
        col = LazyCollection(_make_fetch(["a", "b"], 3), page_size=2)
        assert col[0] == "a"
        assert col[1] == "b"
        assert col[2] == "a"
        assert col[-1] == "a"
        assert col[-2] == "b"
        assert col[-3] == "a"

        with pytest.raises(IndexError):
            col[3]
        with pytest.raises(IndexError):
            col[-4]

    def test_getitem_slice(self):
        col = LazyCollection(_make_fetch([10, 20], 5), page_size=2)
        assert col[1:3] == [20, 10]
        assert col[0:6] == [10, 20, 10, 20, 10]
        assert col[3:] == [20, 10]
        assert col[:2] == [10, 20]

    def test_iter(self):
        col = LazyCollection(_make_fetch([], 0), page_size=10)
        assert list(col) == []
        col = LazyCollection(_make_fetch([1, 2, 3], 6), page_size=10)
        assert list(col) == [1, 2, 3, 1, 2, 3]

    def test_caching_fetch_called_once_per_page(self):
        fetch = MagicMock(side_effect=_make_fetch([1, 2, 3], 10))
        col = LazyCollection(fetch, page_size=10)
        _ = col[0]
        _ = col[1]
        _ = col[2]
        fetch.assert_called_once_with(1, 10)

    def test_page_size_adjusts_to_api_limit(self):
        def fetch(page, page_size):
            items = list(range(0, 10))[: (page - 1) * 5 + 5][(page - 1) * 5 :]
            pg = Pagination(total=10, offset=(page - 1) * 5, limit=5)
            return items, pg

        col = LazyCollection(fetch, page_size=10)
        _ = col[0]
        assert col._page_size == 5
        assert col[5] == 5


class TestLazyPathCollection:
    def test_directory_cache_shared(self):
        mock_client = MagicMock()
        mock_dir = MagicMock(name="parent_dir", parent_id="0")
        mock_client.id.return_value = mock_dir

        entry1 = _SimpleEntry("a.txt", "dir1", "f1", file_client=mock_client)
        entry2 = _SimpleEntry("b.txt", "dir1", "f2", file_client=mock_client)
        col = LazyPathCollection(_make_fetch([entry1, entry2], 2), page_size=10)

        col[0]._get_directory("dir1")
        col[1]._get_directory("dir1")

        mock_client.id.assert_called_once_with("dir1")

    def test_different_directory_ids_each_fetched(self):
        mock_client = MagicMock()
        mock_client.id.side_effect = lambda id: MagicMock(name=id, parent_id="0")

        entry1 = _SimpleEntry("a.txt", "dirA", "f1", file_client=mock_client)
        entry2 = _SimpleEntry("b.txt", "dirB", "f2", file_client=mock_client)
        col = LazyPathCollection(_make_fetch([entry1, entry2], 2), page_size=10)

        col[0]._get_directory("dirA")
        col[1]._get_directory("dirB")

        assert mock_client.id.call_count == 2
        mock_client.id.assert_any_call("dirA")
        mock_client.id.assert_any_call("dirB")
