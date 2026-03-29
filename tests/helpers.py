from cli115.client.lazy import LazyCollection
from cli115.client.models import Pagination


def make_lazy(items, total=None):
    if total is None:
        total = len(items)
    page_size = len(items) if items else 115

    def fetch(page, ps):
        offset = (page - 1) * ps
        sliced = items[offset : offset + ps]
        pg = Pagination(total=total, offset=offset, limit=ps)
        return sliced, pg

    col = LazyCollection(fetch, page_size=page_size)
    if items:
        col._ensure_page(1)
    else:
        col._pagination = Pagination(total=total, offset=0, limit=page_size)
    return col
