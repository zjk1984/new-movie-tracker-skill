# -*- coding: utf-8 -*-
"""GuangYa ``downloads`` JAV → Jellyfin sidecar scrape helpers."""
from __future__ import annotations

import tempfile
from collections import deque
from pathlib import Path
from typing import Any, Callable, Iterator

from guangya_cloud_cli import run_operations, upload_local_file
from guangya_cloud_submit_lib import guangya_folder_from_env
from jellyfin_nfo import is_video_filename
from pikpak_downloads_jav_scrape_lib import (
    fetch_cover_bytes,
    group_videos_by_av,
    is_jav_video_row,
    lookup_scrape_metadata,
    plan_sidecars_for_av,
)

__all__ = [
    "guangya_folder_from_env",
    "list_guangya_dir_paged",
    "walk_guangya_tree",
    "iter_guangya_jav_video_files",
    "guangya_root_sibling_names",
    "group_videos_by_av",
    "lookup_scrape_metadata",
    "plan_sidecars_for_av",
    "fetch_cover_bytes",
    "upload_sidecar_bytes",
]


def list_guangya_dir_paged(
    parent_id: str,
    *,
    runner: Callable[..., Any] | None = None,
    page_size: int = 100,
    max_pages: int = 200,
) -> list[dict[str, Any]]:
    all_items: list[dict[str, Any]] = []
    page = 0
    while page < max_pages:
        code, data, _stderr = run_operations(
            [
                {
                    "id": f"list-{parent_id}-{page}",
                    "type": "list",
                    "remote_parent_id": parent_id,
                    "page": page,
                    "page_size": page_size,
                },
            ],
            runner=runner,
        )
        if code != 0:
            break
        result = ((data.get("data") or {}).get("items") or [{}])[0].get("result") or {}
        items = list(result.get("items") or [])
        all_items.extend(items)
        if len(items) < page_size:
            break
        page += 1
    return all_items


def walk_guangya_tree(
    root_id: str,
    *,
    runner: Callable[..., Any] | None = None,
    include_directories: bool = False,
) -> list[dict[str, Any]]:
    """Depth-first walk; default returns files only."""
    collected: list[dict[str, Any]] = []
    queue: deque[str] = deque([root_id])
    seen: set[str] = set()
    while queue:
        pid = queue.popleft()
        if pid in seen:
            continue
        seen.add(pid)
        for row in list_guangya_dir_paged(pid, runner=runner):
            if row.get("type") == "directory":
                if include_directories:
                    collected.append(row)
                cid = str(row.get("id") or "").strip()
                if cid:
                    queue.append(cid)
            else:
                collected.append(row)
    return collected


def iter_guangya_jav_video_files(
    downloads_parent_id: str,
    *,
    recursive: bool = True,
    runner: Callable[..., Any] | None = None,
    pseudo_as_jav: bool | None = None,
) -> Iterator[tuple[dict[str, Any], str]]:
    """Yield (GuangYa file row, parent_id) for completed JAV videos under ``downloads``."""
    if recursive:
        rows = walk_guangya_tree(downloads_parent_id, runner=runner)
    else:
        rows = list_guangya_dir_paged(downloads_parent_id, runner=runner)

    for row in rows:
        if row.get("type") != "file":
            continue
        name = str(row.get("name") or "")
        if not is_video_filename(name):
            continue
        ok, _av = is_jav_video_row(name, pseudo_as_jav=pseudo_as_jav)
        if not ok:
            continue
        parent_id = str(row.get("parent_id") or downloads_parent_id)
        yield row, parent_id


def guangya_root_sibling_names(
    downloads_parent_id: str,
    *,
    runner: Callable[..., Any] | None = None,
) -> set[str]:
    names: set[str] = set()
    for row in list_guangya_dir_paged(downloads_parent_id, runner=runner):
        name = str(row.get("name") or "")
        if name:
            names.add(name)
    return names


def upload_sidecar_bytes(
    data: bytes,
    filename: str,
    remote_parent_id: str,
    *,
    runner: Callable[..., Any] | None = None,
) -> None:
    suffix = Path(filename).suffix or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(data)
        path = Path(tmp.name)
    try:
        upload_local_file(path, remote_parent_id, runner=runner)
    finally:
        path.unlink(missing_ok=True)
