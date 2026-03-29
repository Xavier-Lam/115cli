from __future__ import annotations

from dataclasses import fields
from typing import Callable, Generic, TYPE_CHECKING, TypeVar

from cli115.client.models import Directory, FileSystemEntry, Pagination

if TYPE_CHECKING:
    from cli115.client.base import FileClient


T = TypeVar("T")


class LazyPathMixin:
    """Mixin that lazily resolves the ``path`` attribute by walking up the
    parent-directory chain via the ``id()`` method.

    Attach a ``FileClient`` instance to ``_file_client`` after construction.
    When ``.path`` is first accessed and is ``None``, the mixin calls
    ``_file_client.id(parent_id)`` recursively up to the root and caches the
    resulting absolute path string so the walk only happens once.
    """

    _file_client: FileClient = None

    @property
    def path(self):
        val = self.__dict__.get("path")
        if val is not None:
            return val
        parts = [self.name]
        parent_id = self.parent_id
        while parent_id and parent_id != "0":
            parent = self._get_directory(parent_id)
            parts.append(parent.name)
            parent_id = parent.parent_id
        val = "/" + "/".join(reversed(parts))
        self.__dict__["path"] = val
        return val

    @path.setter
    def path(self, value):
        pass  # ignore attempts to set path directly

    def _get_directory(self, id: str) -> Directory:
        return self._file_client.id(id)


def new_lazy_cls(item: FileSystemEntry, client: FileClient) -> FileSystemEntry:
    cls = item.__class__
    cls = type(cls.__name__, (LazyPathMixin, cls), {})
    attrs = {f.name: getattr(item, f.name) for f in fields(item)}
    rv = cls(**attrs)
    rv._file_client = client
    return rv


class LazyCollection(Generic[T]):
    """Lazily-loaded, index-accessible collection backed by paginated API calls.

    The collection fetches pages on demand as items are accessed. It uses the
    default page size for all fetches. The fetch callable receives (page, page_size)
    and returns (items, pagination).

    Warning: Avoid fully iterating or calling len() on large collections without
    knowing the total number of items, as this will trigger many API requests.
    """

    def __init__(
        self,
        fetch: Callable[[int, int], tuple[list[T], Pagination]],
        page_size: int,
    ) -> None:
        self._fetch = fetch
        self._page_size = page_size
        self._cache: dict[int, T] = {}
        self._pagination: Pagination | None = None

    def _add(self, idx: int, item: T) -> None:
        self._cache[idx] = item

    def _ensure_page(self, page: int) -> None:
        page_size = self._page_size
        items, pagination = self._fetch(page, page_size)
        if pagination.limit != page_size:
            self._page_size = pagination.limit
        if self._pagination is None or pagination.total != self._pagination.total:
            self._pagination = pagination
        start = (page - 1) * self._page_size
        for i, item in enumerate(items):
            self._add(start + i, item)

    def _ensure_index(self, index: int) -> None:
        if index in self._cache:
            return
        page = index // self._page_size + 1
        self._ensure_page(page)
        if index not in self._cache:
            # page size change may have shifted the page boundaries
            page = index // self._page_size + 1
            self._ensure_page(page)

    def _get_total(self) -> int:
        if self._pagination is None:
            self._ensure_page(1)
        return self._pagination.total  # type: ignore[union-attr]

    def __len__(self) -> int:
        return self._get_total()

    def __getitem__(self, key: int | slice) -> T | list[T]:
        if isinstance(key, slice):
            total = self._get_total()
            indices = range(*key.indices(total))
            result = []
            for i in indices:
                self._ensure_index(i)
                if i not in self._cache:
                    break
                result.append(self._cache[i])
            return result
        if key < 0:
            key = self._get_total() + key
        if key < 0:
            raise IndexError("index out of range")
        self._ensure_index(key)
        if key not in self._cache:
            raise IndexError("unexpected index out of range")
        return self._cache[key]

    def __iter__(self):
        total = self._get_total()
        for i in range(total):
            yield self[i]


class LazyPathCollection(LazyCollection[T]):
    """LazyPathCollection for result sets that caches seen directories."""

    def __init__(
        self,
        fetch: Callable[[int, int], tuple[list[T], Pagination]],
        page_size: int,
    ) -> None:
        super().__init__(fetch, page_size)
        self._dir_cache: dict[str, object] = {}

    def _wrap_item(self, item: T) -> T:
        if not isinstance(item, LazyPathMixin):
            return item
        original_get = item._get_directory.__func__  # type: ignore[attr-defined]

        def cached_get_directory(self_item, id: str):
            if id not in self._dir_cache:
                self._dir_cache[id] = original_get(self_item, id)
            return self._dir_cache[id]

        item.__class__ = type(
            item.__class__.__name__,
            (item.__class__,),
            {"_get_directory": cached_get_directory},
        )
        return item

    def _add(self, idx: int, item: T) -> None:
        wrapped = self._wrap_item(item)
        super()._add(idx, wrapped)
