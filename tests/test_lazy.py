import unittest
from unittest.mock import MagicMock, call

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


class TestLazyPathMixin(unittest.TestCase):

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

        # first access should recursively fetch parent directories
        path = entry.path
        self.assertEqual(path, "/parent/grand/file.txt")
        self.assertEqual(mock_client.id.call_count, 2)
        # ensure calls happened in order
        self.assertEqual(
            [c.args[0] for c in mock_client.id.call_args_list], ["p2", "p1"]
        )

        # subsequent accesses should use cached path and not call API again
        mock_client.id.reset_mock()
        _ = entry.path
        mock_client.id.assert_not_called()


class TestLazyCollection(unittest.TestCase):

    def test_len(self):
        col = LazyCollection(_make_fetch([1, 2, 3], 3), page_size=10)
        self.assertEqual(len(col), 3)
        col = LazyCollection(_make_fetch([1, 2, 3], 50), page_size=3)
        self.assertEqual(len(col), 50)

    def test_getitem(self):
        col = LazyCollection(_make_fetch(["a", "b"], 3), page_size=2)
        self.assertEqual(col[0], "a")
        self.assertEqual(col[1], "b")
        self.assertEqual(col[2], "a")

        # negative
        self.assertEqual(col[-1], "a")
        self.assertEqual(col[-2], "b")
        self.assertEqual(col[-3], "a")

        # out of range
        with self.assertRaises(IndexError):
            col[3]
        with self.assertRaises(IndexError):
            col[-4]

    def test_getitem_slice(self):
        col = LazyCollection(_make_fetch([10, 20], 5), page_size=2)
        self.assertEqual(col[1:3], [20, 10])
        self.assertEqual(col[0:6], [10, 20, 10, 20, 10])
        self.assertEqual(col[3:], [20, 10])
        self.assertEqual(col[:2], [10, 20])

    def test_iter(self):
        col = LazyCollection(_make_fetch([], 0), page_size=10)
        self.assertEqual(list(col), [])
        col = LazyCollection(_make_fetch([1, 2, 3], 6), page_size=10)
        self.assertEqual(list(col), [1, 2, 3, 1, 2, 3])

    def test_caching_fetch_called_once_per_page(self):
        fetch = MagicMock(side_effect=_make_fetch([1, 2, 3], 10))
        col = LazyCollection(fetch, page_size=10)
        _ = col[0]
        _ = col[1]
        _ = col[2]
        fetch.assert_called_once_with(1, 10)

    def test_page_size_adjusts_to_api_limit(self):
        # API returns limit=5 even though we request 10
        def fetch(page, page_size):
            items = list(range(0, 10))[: (page - 1) * 5 + 5][(page - 1) * 5 :]
            pg = Pagination(total=10, offset=(page - 1) * 5, limit=5)
            return items, pg

        col = LazyCollection(fetch, page_size=10)
        _ = col[0]  # page 1 fetched, page_size adjusted to 5
        self.assertEqual(col._page_size, 5)
        self.assertEqual(col[5], 5)  # should fetch page 2


class TestLazyPathCollection(unittest.TestCase):

    def test_directory_cache_shared(self):
        mock_client = MagicMock()
        mock_dir = MagicMock(name="parent_dir", parent_id="0")
        mock_client.id.return_value = mock_dir

        entry1 = _SimpleEntry("a.txt", "dir1", "f1", file_client=mock_client)
        entry2 = _SimpleEntry("b.txt", "dir1", "f2", file_client=mock_client)
        col = LazyPathCollection(_make_fetch([entry1, entry2], 2), page_size=10)

        item1 = col[0]
        item2 = col[1]
        item1._get_directory("dir1")
        item2._get_directory("dir1")

        # Both items share the same dir cache on the collection
        mock_client.id.assert_called_once_with("dir1")

    def test_different_directory_ids_each_fetched(self):
        mock_client = MagicMock()
        mock_client.id.side_effect = lambda id: MagicMock(name=id, parent_id="0")

        entry1 = _SimpleEntry("a.txt", "dirA", "f1", file_client=mock_client)
        entry2 = _SimpleEntry("b.txt", "dirB", "f2", file_client=mock_client)
        col = LazyPathCollection(_make_fetch([entry1, entry2], 2), page_size=10)

        col[0]._get_directory("dirA")
        col[1]._get_directory("dirB")

        self.assertEqual(mock_client.id.call_count, 2)
        mock_client.id.assert_any_call("dirA")
        mock_client.id.assert_any_call("dirB")


if __name__ == "__main__":
    unittest.main()
