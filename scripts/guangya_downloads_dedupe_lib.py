# -*- coding: utf-8 -*-
"""GuangYa ``downloads`` / ``JAV`` / ``Save`` listing helpers for dedupe."""
from __future__ import annotations

import os
from typing import Any, Callable

from guangya_cloud_cli import find_directory_id, list_root_directories
from guangya_downloads_jav_scrape_lib import walk_guangya_tree

from pikpak_downloads_dedupe_lib import (
    DEDUPE_FOLDER_TAG,
    parse_folder_list,
    pick_cross_folder_keeper_and_trash,
)
from pikpak_downloads_jav_scrape_lib import is_jav_video_row, is_video_filename

SAVE_KEEPER_FOLDER = "Save"
DEFAULT_CROSS_FOLDER_PRIORITY = ("downloads", "Save", "JAV")


def folders_present_in_group(rows: list[dict[str, Any]]) -> set[str]:
    out = {str(r.get(DEDUPE_FOLDER_TAG) or "") for r in rows}
    out.discard("")
    return out


def cross_folder_priority_from_env(
    default: tuple[str, ...] = DEFAULT_CROSS_FOLDER_PRIORITY,
) -> list[str]:
    raw = os.environ.get("GUANGYA_DEDUPE_CROSS_PRIORITY", "").strip()
    if not raw:
        return list(default)
    parsed = parse_folder_list(raw)
    return parsed or list(default)


def keeper_folder_for_priority(
    folders_present: set[str],
    folder_priority: list[str],
) -> str | None:
    """Highest-priority configured folder that has a copy in this group."""
    for folder in folder_priority:
        if folder in folders_present:
            return folder
    return None


def cross_folder_dup_groups_tiered(
    av_groups: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Groups spanning two or more folders (keeper resolved per group)."""
    out: dict[str, list[dict[str, Any]]] = {}
    for av, rows in av_groups.items():
        if len(rows) < 2:
            continue
        if len(folders_present_in_group(rows)) < 2:
            continue
        out[av] = rows
    return out


def pick_tiered_cross_folder_keeper_and_trash(
    rows: list[dict[str, Any]],
    *,
    folder_priority: list[str],
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    """Return (keeper_folder_label, keeper_row, trash_rows) using folder priority."""
    folders = folders_present_in_group(rows)
    keeper_folder = keeper_folder_for_priority(folders, folder_priority)
    if not keeper_folder:
        raise ValueError("cross-folder group has no folder in priority list")
    keeper, trash = pick_cross_folder_keeper_and_trash(rows, keeper_folder=keeper_folder)
    return keeper_folder, keeper, trash


def resolve_guangya_folder_id(folder_name: str) -> tuple[str | None, str]:
    """Resolve root folder id; try exact then case-insensitive (``jav`` → ``JAV``)."""
    want = (folder_name or "").strip()
    if not want:
        return None, want
    found = find_directory_id(want)
    if found:
        return found, want
    lower = want.lower()
    for row in list_root_directories():
        if row.get("type") != "directory":
            continue
        name = str(row.get("name") or "")
        if name.lower() == lower:
            rid = str(row.get("id") or "").strip()
            return (rid or None), name
    return None, want


def guangya_row_for_dedupe(row: dict[str, Any], folder_label: str) -> dict[str, Any]:
    """Shape GuangYa list row like PikPak dedupe rows (complete video files only)."""
    return {
        "kind": "drive#file",
        "phase": "PHASE_TYPE_COMPLETE",
        "id": str(row.get("id") or ""),
        "name": str(row.get("name") or ""),
        "size": int(row.get("size") or 0),
        DEDUPE_FOLDER_TAG: folder_label,
    }


def list_jav_video_rows_in_folder(
    folder_id: str,
    folder_label: str,
    *,
    runner: Callable[..., Any] | None = None,
    pseudo_as_jav: bool | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in walk_guangya_tree(folder_id, runner=runner):
        if row.get("type") != "file":
            continue
        name = str(row.get("name") or "")
        if not is_video_filename(name):
            continue
        ok, _av = is_jav_video_row(name, pseudo_as_jav=pseudo_as_jav)
        if not ok:
            continue
        out.append(guangya_row_for_dedupe(row, folder_label))
    return out
