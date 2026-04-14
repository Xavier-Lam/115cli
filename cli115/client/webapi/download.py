from __future__ import annotations

from cli115.api.web.p115client import check_response
from cli115.client.base import DownloadClient
from cli115.client.models import (
    CloudTask,
    Directory,
    DownloadQuota,
    Pagination,
    TaskFilter,
    TaskStatus,
)
from cli115.client.webapi.base import BaseClient
from cli115.client.utils import parse_ts


class WebAPIDownloadClient(DownloadClient, BaseClient):

    def quota(self) -> DownloadQuota:
        resp = self._api.offline_quota_info()
        resp = check_response(resp)
        return DownloadQuota(
            quota=int(resp.get("quota", 0)),
            total=int(resp.get("total", 0)),
        )

    def _list(
        self, page: int = 1, page_size: int = 30, filter: TaskFilter | None = None
    ) -> tuple[list[CloudTask], Pagination]:
        payload = {"page": page, "page_size": page_size}
        if filter is not None:
            payload["stat"] = {
                TaskFilter.COMPLETED: 11,
                TaskFilter.FAILED: 9,
                TaskFilter.RUNNING: 12,
            }[filter]
        resp = self._api.offline_list(payload)
        resp = check_response(resp)
        tasks = [self._parse_task(t) for t in resp.get("tasks") or []]
        page_size = int(resp.get("page_row", resp.get("page_size", page_size)))
        pagination = Pagination(
            total=int(resp.get("count", 0)),
            offset=(int(resp.get("page", 1)) - 1) * page_size,
            limit=page_size,
        )
        return tasks, pagination

    def add_url(
        self, url: str, *, dest_dir: str | Directory | None = None
    ) -> CloudTask:
        payload: dict = {"url": url}
        if dest_dir is not None:
            payload["wp_path_id"] = self._resolve_dir_id(dest_dir)
        resp = self._api.offline_add_url(payload)
        resp = check_response(resp)
        data = resp.get("data", {})
        info_hash = data.get("info_hash", "")
        return self._find_task(info_hash)

    def add_urls(
        self, *urls: str, dest_dir: str | Directory | None = None
    ) -> list[CloudTask]:
        if dest_dir is not None:
            wp_path_id = self._resolve_dir_id(dest_dir)
            resp = self._api.offline_add_urls(list(urls), {"wp_path_id": wp_path_id})
        else:
            resp = self._api.offline_add_urls(list(urls))
        resp = check_response(resp)
        data = resp.get("data", {})
        result = data.get("result", [])
        hashes = [r.get("info_hash", "") for r in result]
        tasks_map = self._fetch_tasks_map()
        return [tasks_map[h] for h in hashes if h in tasks_map]

    def delete(self, *task_hashes: str) -> None:
        resp = self._api.offline_remove(list(task_hashes))
        check_response(resp)

    def clear(self, filter: TaskFilter | None = None) -> None:
        _flag_map: dict[TaskFilter | None, int] = {
            None: 1,
            TaskFilter.COMPLETED: 0,
            TaskFilter.FAILED: 2,
            TaskFilter.RUNNING: 3,
        }
        resp = self._api.offline_clear({"flag": _flag_map[filter]})
        check_response(resp)

    def retry(self, info_hash: str) -> None:
        resp = self._api.offline_restart(info_hash)
        check_response(resp)

    def _find_task(self, info_hash: str) -> CloudTask:
        tasks_map = self._fetch_tasks_map()
        if info_hash in tasks_map:
            return tasks_map[info_hash]
        return CloudTask(
            info_hash=info_hash,
            name="",
            size=0,
            status=TaskStatus.WAITING,
            percent_done=0,
            url="",
        )

    def _fetch_tasks_map(self) -> dict[str, CloudTask]:
        tasks, _ = self._list(page=1)
        return {t.info_hash: t for t in tasks}

    def _parse_task(self, task: dict) -> CloudTask:
        return CloudTask(
            info_hash=task.get("info_hash", ""),
            name=task.get("name", ""),
            size=int(task.get("size", 0)),
            status=TaskStatus(int(task.get("status", 0))),
            percent_done=float(task.get("percentDone", 0)),
            url=task.get("url", ""),
            file_id=str(task.get("file_id", "") or ""),
            pick_code=task.get("pick_code", "") or "",
            folder_id=str(task.get("wp_path_id", "") or ""),
            add_time=parse_ts(task.get("add_time")),
        )
