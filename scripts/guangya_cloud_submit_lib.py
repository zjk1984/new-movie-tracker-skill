#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PikPak downloads 番号 → JavDB magnet fallback → GuangYa cloud add (library)."""
from __future__ import annotations

import copy
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from content_filter import apply_region_filter, is_downloadable
from download_state import extract_btih, item_download_key
from env_utils import SKILL_DIR
from guangya_cloud_cli import find_directory_id, run_operations
from javdb_client import JavDBClient, extract_av_number, is_submit_eligible
from magnet_select import apply_selection, maybe_javdb_magnet_fallback
from pikpak_download import iter_item_downloads, pick_item_download
from pikpak_downloads_dedupe_lib import av_number_for_jav_dedupe, pseudo_as_jav_from_env
from pikpak_downloads_jav_scrape_lib import downloads_folder_from_env

DEFAULT_GUANGYA_FOLDER = "downloads"
DEFAULT_STATE_PATH = SKILL_DIR / "data" / "guangya_submit_state.json"
DEFAULT_FOLDER_ID_CACHE = SKILL_DIR / "data" / "guangya_downloads_folder_id.json"

GUANGYA_SUPPORTED_PREFIXES = (
    "magnet:",
    "ed2k:",
    "ed2k://",
    "http://",
    "https://",
    "ftp://",
    "thunder://",
)


def empty_submit_state() -> dict[str, Any]:
    return {
        "last_run": None,
        "uris": {},
        "av_numbers": {},
    }


def load_submit_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_submit_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_submit_state()
    if not isinstance(data, dict):
        return empty_submit_state()
    data.setdefault("uris", {})
    data.setdefault("av_numbers", {})
    return data


def save_submit_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def state_has_submission(state: dict[str, Any], av_number: str, uri: str) -> bool:
    av = (av_number or "").strip().upper()
    if av and av in (state.get("av_numbers") or {}):
        return True
    key = item_download_key({"uri": uri, "url": uri, "magnet": uri})
    if key and key in (state.get("uris") or {}):
        return True
    btih = extract_btih(uri)
    if btih and f"btih:{btih}" in (state.get("uris") or {}):
        return True
    return False


def mark_state_submitted(
    state: dict[str, Any],
    av_number: str,
    uri: str,
    *,
    task_id: str | None = None,
) -> None:
    av = (av_number or "").strip().upper()
    key = item_download_key({"uri": uri, "url": uri, "magnet": uri}) or f"uri:{uri}"
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    entry = {"uri": uri, "av_number": av, "at": stamp}
    if task_id:
        entry["task_id"] = task_id
    state.setdefault("uris", {})[key] = entry
    if av:
        state.setdefault("av_numbers", {})[av] = key
    state["last_run"] = stamp


def guangya_folder_from_env(default: str = DEFAULT_GUANGYA_FOLDER) -> str:
    return (
        os.environ.get("GUANGYAPAN_FOLDER_DOWNLOADS")
        or os.environ.get("GUANGYA_FOLDER_DOWNLOADS")
        or default
    ).strip() or default


def load_folder_id_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_folder_id_cache(path: Path, folder_name: str, remote_parent_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "folder_name": folder_name,
                "remote_parent_id": remote_parent_id,
                "cached_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def resolve_guangya_parent_id(
    folder_name: str,
    *,
    cache_path: Path | None = None,
    create_if_missing: bool = False,
    runner: Callable[..., Any] | None = None,
) -> str:
    cache_file = cache_path or DEFAULT_FOLDER_ID_CACHE
    cached = load_folder_id_cache(cache_file)
    if (
        cached.get("folder_name") == folder_name
        and cached.get("remote_parent_id")
    ):
        return str(cached["remote_parent_id"])

    found = find_directory_id(folder_name, runner=runner)
    if found:
        save_folder_id_cache(cache_file, folder_name, found)
        return found
    if not create_if_missing:
        raise RuntimeError(
            f"GuangYa folder not found at root: {folder_name!r} "
            "(list remote_parent_id='' or create folder manually)",
        )

    code, data, stderr = run_operations(
        [
            {
                "id": "mkdir-downloads",
                "type": "create_folder",
                "remote_parent_id": "",
                "name": folder_name,
            },
        ],
        runner=runner,
    )
    if code != 0:
        raise RuntimeError(f"create_folder failed: {stderr or data}")
    items = data.get("data", {}).get("items") or []
    result = (items[0].get("result") or {}) if items else {}
    folder_id = str(result.get("fileId") or result.get("file_id") or "").strip()
    if not folder_id:
        raise RuntimeError(f"create_folder returned no id: {data}")
    save_folder_id_cache(cache_file, folder_name, folder_id)
    return folder_id


def load_matched_by_av(scan_path: Path | None) -> dict[str, dict[str, Any]]:
    if scan_path is None or not scan_path.exists():
        return {}
    try:
        data = json.loads(scan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    matched = data.get("matched") or []
    by_av: dict[str, dict[str, Any]] = {}
    for item in matched:
        av = (
            (item.get("av_number") or "")
            or extract_av_number(item.get("title") or "")
            or ""
        ).strip().upper()
        if not av:
            continue
        existing = by_av.get(av)
        if existing is None:
            by_av[av] = item
            continue
        if pick_item_download(item) and not pick_item_download(existing):
            by_av[av] = item
    return by_av


def uri_supported_by_guangya(uri: str) -> bool:
    text = (uri or "").strip().lower()
    return any(text.startswith(prefix) for prefix in GUANGYA_SUPPORTED_PREFIXES)


def _download_row_from_parsed(
    download: dict[str, Any],
    item: dict[str, Any],
) -> dict[str, Any] | None:
    uri = (download.get("uri") or download.get("url") or "").strip()
    if not uri:
        return None
    if uri.lower().startswith("pikpak://"):
        return None
    if not uri_supported_by_guangya(uri):
        return None
    return {
        "name": download.get("name") or item.get("av_number") or "download",
        "title": item.get("title") or "",
        "type": download.get("type") or "url",
        "source": download.get("source") or "",
        "av_number": (download.get("av_number") or item.get("av_number") or "").upper(),
        "uri": uri,
        "url": uri,
    }


def _gate_probe(
    item: dict[str, Any],
    download: dict[str, Any],
    *,
    region_filter: bool,
    javdb_client: JavDBClient | None,
    javdb_score_gate: bool,
) -> tuple[bool, str]:
    probe = dict(item)
    probe["av_number"] = (
        download.get("av_number") or item.get("av_number") or ""
    ).upper()
    if probe["av_number"] and probe.get("number_downloads"):
        title = item.get("title", "download")
        probe["title"] = f"[有码] {probe['av_number']} {title}"
    apply_region_filter(probe, region_filter=region_filter)
    if not is_downloadable(probe):
        return False, probe.get("skip_reason") or "region_excluded"
    if region_filter and javdb_score_gate:
        if not is_submit_eligible(probe, javdb_client, query_if_missing=True):
            return False, probe.get("skip_reason") or "javdb_gate"
    elif region_filter:
        if not is_downloadable(probe):
            return False, "not_downloadable"
    return True, ""


def _rows_from_scan_item(
    item: dict[str, Any],
    *,
    region_filter: bool,
    javdb_client: JavDBClient | None,
    javdb_score_gate: bool,
) -> list[dict[str, Any]]:
    work = copy.deepcopy(item)
    apply_selection(work, javdb_client)
    if not pick_item_download(work):
        maybe_javdb_magnet_fallback(work, javdb_client)
    rows: list[dict[str, Any]] = []
    for download in iter_item_downloads(work):
        ok, reason = _gate_probe(
            work,
            download,
            region_filter=region_filter,
            javdb_client=javdb_client,
            javdb_score_gate=javdb_score_gate,
        )
        if not ok:
            continue
        row = _download_row_from_parsed(download, work)
        if row:
            rows.append(row)
    if rows:
        return rows
    picked = pick_item_download(work)
    if not picked:
        return []
    ok, _reason = _gate_probe(
        work,
        picked,
        region_filter=region_filter,
        javdb_client=javdb_client,
        javdb_score_gate=javdb_score_gate,
    )
    if not ok:
        return []
    row = _download_row_from_parsed(picked, work)
    return [row] if row else []


def _rows_from_javdb_only(
    av_number: str,
    representative_name: str,
    *,
    region_filter: bool,
    javdb_client: JavDBClient | None,
    javdb_score_gate: bool,
) -> tuple[list[dict[str, Any]], str]:
    item: dict[str, Any] = {
        "av_number": av_number.upper(),
        "title": representative_name or av_number,
        "name": av_number.upper(),
    }
    apply_region_filter(item, region_filter=region_filter)
    if not is_downloadable(item):
        return [], item.get("skip_reason") or "region_excluded"
    if region_filter and javdb_score_gate:
        if not is_submit_eligible(item, javdb_client, query_if_missing=True):
            return [], item.get("skip_reason") or "javdb_gate"
    maybe_javdb_magnet_fallback(item, javdb_client)
    if not pick_item_download(item):
        return [], "no_download_link"
    picked = pick_item_download(item)
    assert picked is not None
    ok, reason = _gate_probe(
        item,
        picked,
        region_filter=region_filter,
        javdb_client=javdb_client,
        javdb_score_gate=javdb_score_gate,
    )
    if not ok:
        return [], reason
    row = _download_row_from_parsed(picked, item)
    return ([row] if row else []), ""


def resolve_submit_row_for_av(
    av_number: str,
    *,
    representative_name: str = "",
    scan_item: dict[str, Any] | None = None,
    javdb_client: JavDBClient | None = None,
    region_filter: bool = True,
    javdb_score_gate: bool = True,
) -> tuple[dict[str, Any] | None, str, str]:
    """Return (row, skip_reason, link_source). link_source: scan|javdb|none."""
    av = av_number.strip().upper()
    if scan_item:
        rows = _rows_from_scan_item(
            scan_item,
            region_filter=region_filter,
            javdb_client=javdb_client,
            javdb_score_gate=javdb_score_gate,
        )
        if rows:
            return rows[0], "", "scan"
    rows, reason = _rows_from_javdb_only(
        av,
        representative_name,
        region_filter=region_filter,
        javdb_client=javdb_client,
        javdb_score_gate=javdb_score_gate,
    )
    if rows:
        return rows[0], "", "javdb"
    return None, reason or "no_download_link", "none"


def enumerate_av_numbers_from_files(
    files: list[dict[str, Any]],
    *,
    pseudo_as_jav: bool | None = None,
) -> dict[str, str]:
    """Map 番号 → representative filename (first seen)."""
    pseudo = pseudo_as_jav if pseudo_as_jav is not None else pseudo_as_jav_from_env(None)
    out: dict[str, str] = {}
    for row in files:
        if row.get("kind") != "drive#file":
            continue
        if row.get("phase") != "PHASE_TYPE_COMPLETE":
            continue
        name = str(row.get("name") or "")
        av = av_number_for_jav_dedupe(name, pseudo_as_jav=pseudo)
        if not av:
            av_raw = extract_av_number(name)
            av = av_raw.upper() if av_raw else ""
        if not av:
            continue
        out.setdefault(av, name)
    return out


def cloud_collection_add_operations(
    rows: list[dict[str, Any]],
    remote_parent_id: str,
) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        uri = (row.get("uri") or row.get("url") or "").strip()
        if not uri:
            continue
        op: dict[str, Any] = {
            "id": f"add-{index + 1}",
            "type": "cloud_collection_add",
            "url": uri,
            "remote_parent_id": remote_parent_id,
        }
        name = (row.get("name") or row.get("av_number") or "").strip()
        if name and name != row.get("av_number"):
            op["new_name"] = name
        ops.append(op)
    return ops


def preflight_resolve_operations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        uri = (row.get("uri") or row.get("url") or "").strip()
        if not uri:
            continue
        ops.append({
            "id": f"resolve-{index + 1}",
            "type": "resolve_cloud_collection",
            "url": uri,
        })
    return ops


def extract_task_id_from_run_result(data: dict[str, Any], operation_id: str) -> str:
    for item in data.get("data", {}).get("items") or []:
        if item.get("operation_id") != operation_id:
            continue
        result = item.get("result") or {}
        for key in ("task_id", "remote_task_id", "taskId"):
            val = result.get(key)
            if val:
                return str(val)
    return ""


def submit_rows_to_guangya(
    rows: list[dict[str, Any]],
    *,
    remote_parent_id: str,
    preflight: bool = False,
    runner: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    if not rows:
        return {"submitted": 0, "results": []}

    operations: list[dict[str, Any]] = []
    if preflight:
        operations.extend(preflight_resolve_operations(rows))
    operations.extend(cloud_collection_add_operations(rows, remote_parent_id))

    code, data, stderr = run_operations(operations, runner=runner)
    results: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        op_id = f"add-{index + 1}"
        task_id = extract_task_id_from_run_result(data, op_id)
        results.append({
            "av_number": row.get("av_number"),
            "uri": row.get("uri"),
            "task_id": task_id,
            "operation_id": op_id,
        })
    return {
        "exit_code": code,
        "stderr": stderr,
        "response": data,
        "submitted": len(rows),
        "results": results,
    }
