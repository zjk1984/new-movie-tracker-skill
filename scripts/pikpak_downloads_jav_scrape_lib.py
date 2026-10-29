# -*- coding: utf-8 -*-
"""Helpers for PikPak downloads JAV → Jellyfin sidecar scrape."""
from __future__ import annotations

import os
import time
from collections import deque
from typing import Any, Callable, Iterator

from content_filter import classify_region
from javdb_client import JAV_REPORT_REGIONS, JavDBClient
from jellyfin_nfo import (
    is_video_filename,
    merge_scrape_metadata,
    sidecar_names_for_video,
)
from pikpak_downloads_dedupe_lib import (
    DEFAULT_FOLDER,
    av_number_for_jav_dedupe,
    pseudo_as_jav_from_env,
)

try:
    from curl_cffi import requests as http
except ImportError:
    http = None  # type: ignore[assignment,misc]


def scrape_delay_seconds() -> float:
    raw = os.environ.get("JAVDB_SCRAPE_DELAY", "1.5").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 1.5


def downloads_folder_from_env(default: str = DEFAULT_FOLDER) -> str:
    return (os.environ.get("PIKPAK_DOWNLOADS_FOLDER") or default).strip() or default


def is_jav_video_row(name: str, *, pseudo_as_jav: bool | None = None) -> tuple[bool, str | None]:
    pseudo = pseudo_as_jav if pseudo_as_jav is not None else pseudo_as_jav_from_env(None)
    av = av_number_for_jav_dedupe(name, pseudo_as_jav=pseudo)
    if not av:
        return False, None
    region = classify_region({"title": name, "av_number": av})
    if region not in JAV_REPORT_REGIONS:
        return False, av
    return True, av


def iter_video_files_under_parent(
    list_children: Callable[..., list[dict]],
    session: Any,
    token: str,
    device_id: str,
    user_id: str,
    downloads_parent_id: str,
    *,
    recursive: bool = True,
) -> Iterator[tuple[dict[str, Any], str, bool]]:
    """Yield (file_row, parent_id, subfolder_layout) for JAV videos under downloads."""
    queue: deque[tuple[str, bool]] = deque([(downloads_parent_id, False)])
    while queue:
        parent_id, inside_subfolder = queue.popleft()
        rows = list_children(
            session,
            token,
            device_id,
            user_id,
            parent_id=parent_id,
            complete_files_only=True,
        )
        subfolders: list[str] = []
        for row in rows:
            kind = row.get("kind")
            if kind == "drive#folder":
                if recursive:
                    subfolders.append(str(row.get("id") or ""))
                continue
            if kind != "drive#file":
                continue
            if row.get("phase") != "PHASE_TYPE_COMPLETE":
                continue
            name = str(row.get("name") or "")
            if not is_video_filename(name):
                continue
            ok, _av = is_jav_video_row(name)
            if not ok:
                continue
            yield row, parent_id, inside_subfolder
        for folder_id in subfolders:
            if folder_id:
                queue.append((folder_id, True))


def sibling_name_set(
    list_children: Callable[..., list[dict]],
    session: Any,
    token: str,
    device_id: str,
    user_id: str,
    parent_id: str,
) -> set[str]:
    names: set[str] = set()
    for row in list_children(
        session,
        token,
        device_id,
        user_id,
        parent_id=parent_id,
        complete_files_only=False,
    ):
        name = str(row.get("name") or "")
        if name:
            names.add(name)
    return names


def fetch_cover_bytes(url: str, *, timeout: float = 30.0) -> bytes:
    if not url:
        raise ValueError("empty cover url")
    if http is None:
        raise ImportError("cover download requires curl_cffi")
    resp = http.get(url, impersonate="chrome120", timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"cover HTTP {resp.status_code}")
    data = resp.content
    if not data:
        raise RuntimeError("empty cover body")
    return data


def lookup_scrape_metadata(
    client: JavDBClient,
    number: str,
    *,
    sleep_fn: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    info = client.lookup(number, fetch_magnets=False, exact=True)
    delay = scrape_delay_seconds()
    if sleep_fn and delay > 0:
        sleep_fn(delay)
    movie_id = str(info.get("javdb_id") or "")
    detail: dict[str, Any] = {}
    if movie_id:
        detail = client.movie_detail(movie_id)
        if sleep_fn and delay > 0:
            sleep_fn(delay)
    return merge_scrape_metadata(info, detail)


def plan_sidecars_for_video(
    video_row: dict[str, Any],
    parent_id: str,
    *,
    subfolder_layout: bool,
    existing_names: set[str],
    include_fanart: bool,
) -> dict[str, Any]:
    video_name = str(video_row.get("name") or "")
    sidecars = sidecar_names_for_video(video_name, subfolder_layout=subfolder_layout)
    plan: dict[str, Any] = {
        "video_id": video_row.get("id"),
        "video_name": video_name,
        "parent_id": parent_id,
        "subfolder_layout": subfolder_layout,
        "sidecars": sidecars,
        "needs_nfo": sidecars["nfo"] not in existing_names,
        "needs_poster": sidecars["poster"] not in existing_names,
        "needs_fanart": include_fanart and sidecars["fanart"] not in existing_names,
    }
    return plan
