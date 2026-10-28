# -*- coding: utf-8 -*-
"""Pure helpers for PikPak downloads dedupe (JAV: UC > C > size; domestic: size > name)."""
from __future__ import annotations

import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from content_filter import (
    STUDIO_NUM_RE,
    domestic_keep_reason,
    is_domestic_context,
    is_pseudo_jav,
)
from download_state import extract_btih
from javdb_client import extract_av_number

DEFAULT_FOLDER = "downloads"
DEFAULT_DOMESTIC_SMALL_FOLDERS = "My Pack"
DOMESTIC_SMALL_MIN_BYTES_DEFAULT = 30 * 1024 * 1024
DOWNLOADS_KEEPER_FOLDER = "downloads"
DEDUPE_FOLDER_TAG = "_dedupe_folder"


def parse_folder_list(raw: str) -> list[str]:
    """Parse comma-separated PikPak folder names (dedupe order preserved)."""
    parts = [p.strip() for p in str(raw or "").split(",")]
    return [p for p in parts if p]


def folders_from_env() -> list[str] | None:
    raw = os.environ.get("PIKPAK_DEDUPE_FOLDERS", "").strip()
    if not raw:
        return None
    parsed = parse_folder_list(raw)
    return parsed or None


def tag_row_folder(row: dict[str, Any], folder: str) -> dict[str, Any]:
    tagged = dict(row)
    tagged[DEDUPE_FOLDER_TAG] = folder
    return tagged


def cross_folder_dup_groups(
    av_groups: dict[str, list[dict[str, Any]]],
    *,
    keeper_folder: str = DOWNLOADS_KEEPER_FOLDER,
) -> dict[str, list[dict[str, Any]]]:
    """Groups spanning multiple folders where keeper_folder is present."""
    out: dict[str, list[dict[str, Any]]] = {}
    for av, rows in av_groups.items():
        if len(rows) < 2:
            continue
        folders_present = {str(r.get(DEDUPE_FOLDER_TAG) or "") for r in rows}
        folders_present.discard("")
        if len(folders_present) < 2:
            continue
        if keeper_folder not in folders_present:
            continue
        out[av] = rows
    return out


def pick_cross_folder_keeper_and_trash(
    rows: list[dict[str, Any]],
    *,
    keeper_folder: str = DOWNLOADS_KEEPER_FOLDER,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Keep best file in keeper_folder only; trash all other folders + extras in keeper."""
    in_keeper = [r for r in rows if str(r.get(DEDUPE_FOLDER_TAG) or "") == keeper_folder]
    if not in_keeper:
        raise ValueError(f"cross-folder group has no files in keeper folder {keeper_folder!r}")
    other = [r for r in rows if str(r.get(DEDUPE_FOLDER_TAG) or "") != keeper_folder]
    if len(in_keeper) == 1:
        keeper = in_keeper[0]
        trash = list(other)
    else:
        keeper, trash_in_keeper = pick_keeper_and_trash(in_keeper)
        trash = list(other) + trash_in_keeper
    return keeper, trash


def group_tagged_files_by_av_number(
    rows: list[dict[str, Any]],
    *,
    pseudo_as_jav: bool | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    """Like group_files_by_av_number but rows may already be folder-tagged."""
    pseudo_jav = pseudo_as_jav if pseudo_as_jav is not None else pseudo_as_jav_from_env(None)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skipped = 0
    for row in rows:
        if row.get("kind") != "drive#file":
            continue
        if row.get("phase") != "PHASE_TYPE_COMPLETE":
            continue
        name = str(row.get("name") or "")
        av = av_number_for_jav_dedupe(name, pseudo_as_jav=pseudo_jav)
        if not av:
            skipped += 1
            continue
        groups[av].append(row)
    return dict(groups), skipped


def within_folder_enabled_from_env() -> bool:
    return os.environ.get("PIKPAK_DEDUPE_WITHIN_FOLDER", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def cross_folder_enabled_from_env() -> bool:
    return os.environ.get("PIKPAK_DEDUPE_CROSS_FOLDER", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }

DOMESTIC_MIN_NORMALIZED_LEN = 8

_UC_SUFFIX_RE = re.compile(r"-UC(?:$|[-_.])", re.IGNORECASE)
_C_SUFFIX_RE = re.compile(r"-C$", re.IGNORECASE)

_SITE_PREFIX_RE = re.compile(
    r"^(?:[a-z0-9][a-z0-9.-]*\.(?:com|cc|net|org|tv|me|vip|xyz|top|pw|io)@)+",
    re.IGNORECASE,
)
_RESOLUTION_TOKEN_RE = re.compile(
    r"\b(?:1080[pP]|720[pP]|2160[pP]|4320[pP]|4[kK]|8[kK]|"
    r"[hH][dD]|[fF][hH][dD]|[uU][hH][dD]|"
    r"[xX]26[45]|[hH]\.?26[45]|[hH][eE][vV][cC])\b",
)
_BRACKET_NOISE_RE = re.compile(r"[\[\]()【】（）{}「」『』]")
_COPY_SUFFIX_RE = re.compile(r"\(\d+\)(?=\.[^.]+$|$)")
_DUP_SPACE_RE = re.compile(r"\s+")


def _basename_stem(name: str) -> str:
    base = Path(name).name
    if "." in base:
        return base.rsplit(".", 1)[0]
    return base


def normalize_domestic_filename(name: str) -> str:
    """Normalize domestic/no-av filenames for fuzzy duplicate grouping."""
    base = Path(name).name
    if "." in base:
        stem, ext = base.rsplit(".", 1)
        ext_lower = ext.lower()
    else:
        stem, ext_lower = base, ""

    text = stem
    text = _SITE_PREFIX_RE.sub("", text)
    text = _BRACKET_NOISE_RE.sub(" ", text)
    text = _RESOLUTION_TOKEN_RE.sub(" ", text)
    text = _COPY_SUFFIX_RE.sub("", text.strip())
    text = _DUP_SPACE_RE.sub(" ", text).strip()
    if ext_lower:
        return f"{text}.{ext_lower}".lower()
    return text.lower()


def extract_btih_from_filename(name: str) -> str | None:
    return extract_btih(name)


def domestic_group_key(
    row: dict[str, Any],
    *,
    min_normalized_len: int = DOMESTIC_MIN_NORMALIZED_LEN,
) -> str:
    """Grouping key for domestic dedupe (first match wins)."""
    name = str(row.get("name") or "")
    fid = str(row.get("id") or "unknown")

    btih = extract_btih_from_filename(name)
    if btih:
        return f"btih:{btih.upper()}"

    file_hash = str(row.get("hash") or row.get("md5") or "").strip()
    if file_hash:
        return f"hash:{file_hash.upper()}"

    norm = normalize_domestic_filename(name)
    if len(norm) >= min_normalized_len:
        return f"title:{norm}"

    return f"id:{fid}"


def pseudo_as_jav_from_env(value: str | None) -> bool:
    if value is None:
        value = os.environ.get("PIKPAK_DEDUPE_PSEUDO_AS_JAV", "")
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def av_number_for_jav_dedupe(name: str, *, pseudo_as_jav: bool) -> str | None:
    av = extract_av_number(name)
    if not av:
        return None
    if not pseudo_as_jav and is_pseudo_jav(name, av):
        return None
    return av


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


def domestic_dedupe_sort_key(file_row: dict[str, Any]) -> tuple[int, str]:
    """Domestic keeper: size desc, name asc."""
    name = str(file_row.get("name") or "")
    size = int(file_row.get("size") or 0)
    return (-size, name)


def pick_keeper_and_trash(files: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if len(files) < 2:
        raise ValueError("pick_keeper_and_trash requires at least two files")
    ordered = sorted(files, key=dedupe_sort_key)
    keeper = ordered[0]
    trash = ordered[1:]
    return keeper, trash


def pick_keeper_and_trash_domestic(
    files: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if len(files) < 2:
        raise ValueError("pick_keeper_and_trash_domestic requires at least two files")
    ordered = sorted(files, key=domestic_dedupe_sort_key)
    keeper = ordered[0]
    trash = ordered[1:]
    return keeper, trash


def _complete_file_rows(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in files:
        if row.get("kind") != "drive#file":
            continue
        if row.get("phase") != "PHASE_TYPE_COMPLETE":
            continue
        out.append(row)
    return out


def group_files_by_av_number(
    files: list[dict[str, Any]],
    *,
    pseudo_as_jav: bool | None = None,
) -> tuple[dict[str, list[dict]], int]:
    pseudo_jav = pseudo_as_jav if pseudo_as_jav is not None else pseudo_as_jav_from_env(None)
    groups: dict[str, list[dict]] = defaultdict(list)
    skipped = 0
    for row in _complete_file_rows(files):
        name = str(row.get("name") or "")
        av = av_number_for_jav_dedupe(name, pseudo_as_jav=pseudo_jav)
        if not av:
            skipped += 1
            continue
        groups[av].append(row)
    return dict(groups), skipped


def group_files_domestic(
    files: list[dict[str, Any]],
    *,
    pseudo_as_jav: bool | None = None,
    min_normalized_len: int = DOMESTIC_MIN_NORMALIZED_LEN,
) -> tuple[dict[str, list[dict]], int]:
    """Group completed files without a JAV av_number (incl. pseudo when pseudo_as_jav=0)."""
    pseudo_jav = pseudo_as_jav if pseudo_as_jav is not None else pseudo_as_jav_from_env(None)
    groups: dict[str, list[dict]] = defaultdict(list)
    candidates = 0
    for row in _complete_file_rows(files):
        name = str(row.get("name") or "")
        if av_number_for_jav_dedupe(name, pseudo_as_jav=pseudo_jav):
            continue
        candidates += 1
        key = domestic_group_key(row, min_normalized_len=min_normalized_len)
        groups[key].append(row)
    return dict(groups), candidates


def domestic_small_folders_from_env() -> list[str]:
    raw = os.environ.get(
        "PIKPAK_DEDUPE_DOMESTIC_FOLDERS",
        DEFAULT_DOMESTIC_SMALL_FOLDERS,
    ).strip()
    parsed = parse_folder_list(raw)
    return parsed or [DEFAULT_DOMESTIC_SMALL_FOLDERS]


def domestic_small_min_bytes_from_env() -> int:
    raw_bytes = os.environ.get("PIKPAK_DEDUPE_DOMESTIC_MIN_BYTES", "").strip()
    if raw_bytes:
        try:
            return max(0, int(raw_bytes))
        except ValueError:
            pass
    raw_mb = os.environ.get("PIKPAK_DEDUPE_DOMESTIC_MIN_MB", "").strip()
    if raw_mb:
        try:
            return max(0, int(float(raw_mb) * 1024 * 1024))
        except ValueError:
            pass
    return DOMESTIC_SMALL_MIN_BYTES_DEFAULT


def domestic_small_enabled_from_env() -> bool:
    return os.environ.get("PIKPAK_DEDUPE_DOMESTIC_SMALL", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def file_row_size_bytes(row: dict[str, Any]) -> int | None:
    """Return size in bytes, or None when missing/invalid/zero (do not trash)."""
    raw = row.get("size")
    if raw is None or raw == "":
        return None
    try:
        size = int(raw)
    except (TypeError, ValueError):
        return None
    if size <= 0:
        return None
    return size


def is_pure_jav_studio_number_filename(name: str) -> bool:
    """True when filename is essentially a Japanese studio 番号 with no domestic context."""
    num = extract_av_number(name)
    if not num:
        return False
    if domestic_keep_reason(name, num):
        return False
    if is_domestic_context(name):
        return False
    if not STUDIO_NUM_RE.match(num):
        return False
    stem = _basename_stem(name)
    stem_u = stem.upper()
    num_u = num.upper()
    if stem_u == num_u:
        return True
    for suffix in ("-UC", "-C", "-U"):
        if stem_u == num_u + suffix:
            return True
    stripped = _SITE_PREFIX_RE.sub("", stem)
    stripped = _BRACKET_NOISE_RE.sub(" ", stripped)
    stripped = _RESOLUTION_TOKEN_RE.sub(" ", stripped)
    stripped = _DUP_SPACE_RE.sub(" ", stripped).strip()
    stripped_u = stripped.upper()
    if stripped_u == num_u:
        return True
    for suffix in ("-UC", "-C", "-U"):
        if stripped_u == num_u + suffix:
            return True
    return False


def qualifies_domestic_small_purge_name(name: str, *, pseudo_as_jav: bool) -> bool:
    if av_number_for_jav_dedupe(name, pseudo_as_jav=pseudo_as_jav):
        return False
    if is_pure_jav_studio_number_filename(name):
        return False
    if domestic_keep_reason(name):
        return True
    if is_domestic_context(name) and not is_pure_jav_studio_number_filename(name):
        return True
    return False


def domestic_small_trash_candidate(
    row: dict[str, Any],
    *,
    min_bytes: int,
    pseudo_as_jav: bool,
) -> bool:
    if row.get("kind") != "drive#file":
        return False
    if row.get("phase") != "PHASE_TYPE_COMPLETE":
        return False
    name = str(row.get("name") or "")
    if not qualifies_domestic_small_purge_name(name, pseudo_as_jav=pseudo_as_jav):
        return False
    size = file_row_size_bytes(row)
    if size is None:
        return False
    return size < min_bytes


def collect_domestic_small_trash_candidates(
    files: list[dict[str, Any]],
    *,
    min_bytes: int | None = None,
    pseudo_as_jav: bool | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (candidates, size_missing_rows) for domestic small-file purge."""
    pseudo_jav = pseudo_as_jav if pseudo_as_jav is not None else pseudo_as_jav_from_env(None)
    threshold = min_bytes if min_bytes is not None else domestic_small_min_bytes_from_env()
    candidates: list[dict[str, Any]] = []
    size_missing: list[dict[str, Any]] = []
    for row in files:
        if row.get("kind") != "drive#file":
            continue
        if row.get("phase") != "PHASE_TYPE_COMPLETE":
            continue
        name = str(row.get("name") or "")
        if not qualifies_domestic_small_purge_name(name, pseudo_as_jav=pseudo_jav):
            continue
        size = file_row_size_bytes(row)
        if size is None:
            size_missing.append(row)
            continue
        if size < threshold:
            candidates.append(row)
    return candidates, size_missing
