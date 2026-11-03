# -*- coding: utf-8 -*-
"""GuangYa ``downloads`` / ``JAV`` / ``Save`` listing helpers for dedupe."""
from __future__ import annotations

import os
from typing import Any, Callable, Literal

from guangya_cloud_cli import find_directory_id, list_root_directories
from guangya_downloads_jav_scrape_lib import walk_guangya_tree

from pikpak_downloads_dedupe_lib import DEDUPE_FOLDER_TAG, DOWNLOADS_KEEPER_FOLDER
from pikpak_downloads_jav_scrape_lib import is_jav_video_row, is_video_filename

SAVE_KEEPER_FOLDER = "Save"
GuangyaCrossPass = Literal["downloads", "save"]


def folders_present_in_group(rows: list[dict[str, Any]]) -> set[str]:
    out = {str(r.get(DEDUPE_FOLDER_TAG) or "") for r in rows}
    out.discard("")
    return out


def cross_folder_dup_groups_guangya_pass(
    av_groups: dict[str, list[dict[str, Any]]],
    *,
    cross_pass: GuangyaCrossPass,
    downloads_folder: str = DOWNLOADS_KEEPER_FOLDER,
    save_folder: str = SAVE_KEEPER_FOLDER,
) -> dict[str, list[dict[str, Any]]]:
    """GuangYa two-pass cross dedupe: downloads-keeper vs Save-keeper."""
    out: dict[str, list[dict[str, Any]]] = {}
    for av, rows in av_groups.items():
        if len(rows) < 2:
            continue
        folders = folders_present_in_group(rows)
        if len(folders) < 2:
            continue
        if cross_pass == "downloads":
            if downloads_folder not in folders or save_folder in folders:
                continue
        elif cross_pass == "save":
            if save_folder not in folders:
                continue
        else:
            raise ValueError(f"unknown cross_pass {cross_pass!r}")
        out[av] = rows
    return out


def cross_folder_save_keeper_enabled_from_env() -> bool:
    return os.environ.get("GUANGYA_DEDUPE_CROSS_SAVE_KEEPER", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


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
