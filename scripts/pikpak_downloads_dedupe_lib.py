# -*- coding: utf-8 -*-
"""Pure helpers for PikPak downloads dedupe (UC > C > size)."""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from javdb_client import extract_av_number

DEFAULT_FOLDER = "downloads"

_UC_SUFFIX_RE = re.compile(r"-UC(?:$|[-_.])", re.IGNORECASE)
_C_SUFFIX_RE = re.compile(r"-C$", re.IGNORECASE)


def _basename_stem(name: str) -> str:
    base = Path(name).name
    if "." in base:
        return base.rsplit(".", 1)[0]
    return base


def classify_filename_variant(name: str) -> int:
    """Return variant rank: UC=2, C=1, neutral=0."""
    stem_u = _basename_stem(name).upper()
    if stem_u.endswith("-UC") or _UC_SUFFIX_RE.search(stem_u):
        return 2
    if stem_u.endswith("-C") and not stem_u.endswith("-UC"):
        return 1
    if _C_SUFFIX_RE.search(stem_u) and "-UC" not in stem_u:
        return 1
    return 0


def dedupe_sort_key(file_row: dict[str, Any]) -> tuple[int, int, str]:
    """Sort key: variant_rank desc, size desc, name asc (for stable keeper pick)."""
    name = str(file_row.get("name") or "")
    size = int(file_row.get("size") or 0)
    rank = classify_filename_variant(name)
    return (-rank, -size, name)


def pick_keeper_and_trash(files: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if len(files) < 2:
        raise ValueError("pick_keeper_and_trash requires at least two files")
    ordered = sorted(files, key=dedupe_sort_key)
    keeper = ordered[0]
    trash = ordered[1:]
    return keeper, trash


def group_files_by_av_number(files: list[dict[str, Any]]) -> tuple[dict[str, list[dict]], int]:
    groups: dict[str, list[dict]] = defaultdict(list)
    skipped = 0
    for row in files:
        if row.get("kind") != "drive#file":
            continue
        if row.get("phase") != "PHASE_TYPE_COMPLETE":
            continue
        av = extract_av_number(str(row.get("name") or ""))
        if not av:
            skipped += 1
            continue
        groups[av].append(row)
    return dict(groups), skipped
