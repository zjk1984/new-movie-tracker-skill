#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Daily scan → GuangYa ``cloud_collection_add`` via guangyapan-drive Skill CLI."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from guangya_cloud_submit_lib import (
    resolve_guangya_parent_id,
    submit_rows_to_guangya,
    uri_supported_by_guangya,
)
from guangya_folder import (
    guangya_folder_for_download_item,
    resolve_cloud_parent_override,
    resolve_guangya_folder,
)
from pikpak_download import item_submit_uri, load_downloads_from_result, save_download_report


def cloud_apply_enabled() -> bool:
    if (os.environ.get("GUANGYA_CLOUD_DRY_RUN") or "").strip().lower() in {"1", "true", "yes"}:
        return False
    raw = (os.environ.get("GUANGYA_CLOUD_APPLY") or "").strip().lower()
    if raw in {"0", "false", "no"}:
        return False
    return True


def item_to_cloud_row(item: dict[str, Any]) -> dict[str, Any] | None:
    uri = item_submit_uri(item)
    if not uri or not uri_supported_by_guangya(uri):
        return None
    name = (item.get("name") or item.get("title") or uri[:80]).strip()
    av = (item.get("av_number") or "").strip()
    return {
        "uri": uri,
        "url": uri,
        "name": name,
        "av_number": av,
        "source": item.get("source"),
        "region": item.get("region") or item.get("content_region"),
    }


def resolve_remote_parent_id(folder_name: str) -> str:
    _name_override, id_override = resolve_cloud_parent_override()
    if id_override:
        return id_override
    target = _name_override or folder_name
    return resolve_guangya_parent_id(target, create_if_missing=False)


def submit_from_result(
    result_path: Path,
    *,
    folder: str | None = None,
    today_only: bool = True,
    region_filter: bool = True,
    new_only: bool = False,
    skip_scan_repeat: bool = True,
    state_file: Path | None = None,
    dry_run: bool | None = None,
) -> tuple[int, int]:
    from download_state import (
        default_state_path,
        filter_new_items,
        load_state,
        mark_submitted,
        save_state,
        touch_run,
    )

    report_path = result_path.parent / "download_report.json"
    folder_label = resolve_guangya_folder(folder)
    apply = cloud_apply_enabled() if dry_run is None else not dry_run

    items = load_downloads_from_result(
        result_path,
        today_only=today_only,
        region_filter=region_filter,
    )
    if skip_scan_repeat:
        from scan_delta import filter_new_download_items

        before_scan = len(items)
        items, scan_repeat = filter_new_download_items(items, result_path.parent)
        if scan_repeat:
            print(
                f"[info] scan dedup: skipped {scan_repeat}/{before_scan} download(s) "
                f"already in previous scan",
            )

    state_path = state_file or default_state_path(result_path.parent)
    state = load_state(state_path) if new_only else None
    if new_only and state is not None:
        before = len(items)
        items = filter_new_items(items, state)
        print(f"[info] new-only: {len(items)}/{before} download(s) since last run")

    fallback_folder = folder_label
    _parent_name, parent_id_override = resolve_cloud_parent_override()
    buckets: dict[str, list[dict[str, Any]]] = {}

    succeeded: list[dict] = []
    failed: list[dict] = []

    for item in items:
        if parent_id_override:
            folder_name = _parent_name or fallback_folder
        else:
            folder_name = guangya_folder_for_download_item(item, fallback=fallback_folder)
        row = item_to_cloud_row(item)
        if not row:
            failed.append(
                {
                    **dict(item),
                    "status": "failed",
                    "error": "unsupported or missing URI for GuangYa cloud add",
                    "folder": folder_name,
                },
            )
            continue
        buckets.setdefault(folder_name, []).append(row)

    total = sum(len(v) for v in buckets.values()) + len(failed)
    if not buckets and not failed:
        print("[info] no downloads to submit")
        save_download_report(
            report_path,
            succeeded=[],
            failed=[],
            folder=folder_label,
            source=str(result_path),
            provider="guangya",
        )
        if new_only and state is not None:
            touch_run(state)
            save_state(state_path, state)
        return 0, 0

    for folder_name, rows in sorted(buckets.items()):
        try:
            remote_parent_id = (
                parent_id_override if parent_id_override else resolve_remote_parent_id(folder_name)
            )
        except RuntimeError as exc:
            err = str(exc)
            print(f"[err] guangya folder {folder_name!r}: {err}", file=sys.stderr)
            for row in rows:
                failed.append({**row, "status": "failed", "error": err, "folder": folder_name})
            continue

        print(
            f"[info] guangya cloud add: {len(rows)} link(s) → {folder_name} ({remote_parent_id})"
            f"{' [dry-run]' if not apply else ''}",
        )
        if not apply:
            for row in rows:
                print(f"[plan] {row.get('name') or row.get('uri', '')[:60]}")
            continue

        submit_result = submit_rows_to_guangya(rows, remote_parent_id=remote_parent_id)
        exit_code = int(submit_result.get("exit_code") or 0)
        if exit_code != 0:
            stderr = submit_result.get("stderr") or submit_result.get("response")
            print(f"[err] guangya batch failed: {stderr}", file=sys.stderr)

        for res in submit_result.get("results") or []:
            uri = res.get("uri") or ""
            task_id = res.get("task_id") or ""
            label = res.get("av_number") or uri[:60]
            print(f"[ok] {label} task={task_id or '?'}")
            record = {
                "uri": uri,
                "url": uri,
                "magnet": uri,
                "status": "ok",
                "task_id": task_id,
                "phase": "submitted",
                "folder": folder_name,
            }
            succeeded.append(record)

    ok = len(succeeded)
    if not apply:
        planned = sum(len(v) for v in buckets.values())
        print(f"[info] guangya dry-run: {planned} link(s) planned (set GUANGYA_CLOUD_APPLY=1 to submit)")
        save_download_report(
            report_path,
            succeeded=[],
            failed=[],
            folder=folder_label,
            source=str(result_path),
            provider="guangya",
            pending_submit=[row for rows in buckets.values() for row in rows],
            submit_skip_reason="dry_run" if planned else "",
        )
        return 0, planned

    save_download_report(
        report_path,
        succeeded=succeeded,
        failed=failed,
        folder=folder_label,
        source=str(result_path),
        provider="guangya",
    )
    print(f"[info] download report: {report_path}")
    if new_only and state is not None:
        if succeeded:
            mark_submitted(state, succeeded)
        touch_run(state)
        save_state(state_path, state)
    return ok, total if total else ok + len(failed)


def extract_pending_submit_uris(report: dict) -> list[str]:
    from guangya_download import extract_pending_submit_uris as _extract

    return _extract(report)
