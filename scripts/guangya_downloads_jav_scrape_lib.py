# -*- coding: utf-8 -*-
"""GuangYa ``downloads`` JAV → Jellyfin sidecar scrape helpers."""
from __future__ import annotations

import tempfile
import xml.etree.ElementTree as ET
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
    "build_root_file_index",
    "nfo_xml_title_japanese",
    "root_nfo_needs_retranslate",
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
    return build_root_file_index(downloads_parent_id, runner=runner)[0]


def build_root_file_index(
    downloads_parent_id: str,
    *,
    runner: Callable[..., Any] | None = None,
) -> tuple[set[str], dict[str, str]]:
    """Return (root file names, name → remote file id) for direct children."""
    names: set[str] = set()
    by_name: dict[str, str] = {}
    for row in list_guangya_dir_paged(downloads_parent_id, runner=runner):
        name = str(row.get("name") or "")
        if not name:
            continue
        names.add(name)
        if row.get("type") == "file":
            fid = str(row.get("id") or "").strip()
            if fid:
                by_name[name] = fid
    return names, by_name


def fetch_guangya_file_text(
    remote_id: str,
    *,
    runner: Callable[..., Any] | None = None,
) -> str:
    code, data, _stderr = run_operations(
        [{"id": "return-text", "type": "return_text", "remote_id": remote_id}],
        runner=runner,
    )
    if code != 0:
        return ""
    items = (data.get("data") or {}).get("items") or []
    if not items:
        return ""
    result = items[0].get("result") or {}
    return str(result.get("content") or "")


def nfo_xml_title_japanese(nfo_text: str) -> bool:
    """True when ``<title>`` or ``<originaltitle>`` still contains hiragana/katakana."""
    from title_translate import has_japanese

    if not (nfo_text or "").strip():
        return False
    try:
        root = ET.fromstring(nfo_text.encode("utf-8"))
    except ET.ParseError:
        return False
    for tag in ("title", "originaltitle"):
        el = root.find(tag)
        if el is not None and el.text and has_japanese(el.text):
            return True
    return False


def root_nfo_needs_retranslate(
    nfo_filename: str,
    *,
    root_file_ids: dict[str, str],
    runner: Callable[..., Any] | None = None,
) -> bool:
    remote_id = root_file_ids.get(nfo_filename)
    if not remote_id:
        return False
    text = fetch_guangya_file_text(remote_id, runner=runner)
    return nfo_xml_title_japanese(text)


def upload_sidecar_bytes(
    data: bytes,
    filename: str,
    remote_parent_id: str,
    *,
    runner: Callable[..., Any] | None = None,
) -> None:
    """Upload bytes using ``filename`` as the remote object name (Skill uses local basename)."""
    name = Path(filename).name
    if not name or name != filename or name in {".", ".."}:
        raise ValueError(f"invalid sidecar filename: {filename!r}")
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / name
        path.write_bytes(data)
        upload_local_file(path, remote_parent_id, runner=runner)
