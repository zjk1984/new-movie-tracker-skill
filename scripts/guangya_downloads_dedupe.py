#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deduplicate GuangYa ``downloads``, ``JAV``, and ``Save`` JAV videos (UC > C > size).

Phase 1: within each folder, trash duplicate 番号 copies.
Phase 2: cross-folder among configured folders — keeper folder = highest priority present
(default priority ``downloads`` > ``Save`` > ``JAV``; override ``GUANGYA_DEDUPE_CROSS_PRIORITY``).
Keep best file in keeper folder; trash lower-priority folders (+ extras in keeper).

Default: dry-run. Pass ``--apply`` to delete via guangyapan-drive Skill ``delete_files``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from env_utils import load_env_local

load_env_local()

from guangya_cloud_cli import delete_remote_files, login_status  # noqa: E402
from guangya_downloads_dedupe_lib import (  # noqa: E402
    cross_folder_dup_groups_tiered,
    cross_folder_priority_from_env,
    list_jav_video_rows_in_folder,
    pick_tiered_cross_folder_keeper_and_trash,
    resolve_guangya_folder_id,
)
from pikpak_downloads_dedupe_lib import (  # noqa: E402
    DEDUPE_FOLDER_TAG,
    cross_folder_enabled_from_env,
    group_tagged_files_by_av_number,
    parse_folder_list,
    pick_keeper_and_trash,
    pseudo_as_jav_from_env,
    within_folder_enabled_from_env,
)


def _trash_rows(
    rows: list[dict[str, Any]],
    *,
    apply: bool,
    trash_ids: set[str],
    trashed_ok: list[int],
) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    to_delete: list[str] = []
    for row in rows:
        fid = str(row.get("id") or "")
        name = str(row.get("name") or "")
        action = "trash" if apply else "would-trash"
        print(f"  [{action}] {name!r} id={fid}")
        trashed = False
        if apply and fid and fid not in trash_ids:
            to_delete.append(fid)
        details.append({"name": name, "id": fid, "trashed_ok": None if not apply else trashed})
    if apply and to_delete:
        try:
            result = delete_remote_files(to_delete)
            deleted = int(result.get("deleted") or 0)
            trashed_ok[0] += deleted
            for fid in to_delete[:deleted]:
                trash_ids.add(fid)
            for item in details:
                if item["id"] in trash_ids:
                    item["trashed_ok"] = True
        except Exception as exc:
            print(f"  [err] delete_files batch failed: {exc}", file=sys.stderr)
    return details


def run_dedupe(
    *,
    folders: list[str],
    apply: bool,
    within_folder: bool,
    cross_folder: bool,
    cross_folder_priority: list[str],
) -> dict[str, Any]:
    _, login_payload, _ = login_status()
    logged_in = (login_payload.get("data") or {}).get("logged_in")
    if not logged_in:
        raise RuntimeError("GuangYa not logged in (guangyapan-drive login-status)")

    pseudo = pseudo_as_jav_from_env(None)
    tagged: list[dict[str, Any]] = []
    folder_ids: dict[str, str] = {}
    for folder in folders:
        fid, resolved = resolve_guangya_folder_id(folder)
        if not fid:
            raise RuntimeError(f"GuangYa folder not found at root: {folder!r}")
        folder_ids[resolved] = fid
        rows = list_jav_video_rows_in_folder(fid, resolved, pseudo_as_jav=pseudo)
        tagged.extend(rows)

    av_groups, skipped = group_tagged_files_by_av_number(tagged, pseudo_as_jav=pseudo)
    stats: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run",
        "folders": folders,
        "folder_ids": folder_ids,
        "files_seen": len(tagged),
        "av_groups": len(av_groups),
        "skipped_non_av": skipped,
        "within_groups": 0,
        "cross_groups": 0,
        "cross_folder_priority": list(cross_folder_priority),
        "cross_groups_by_keeper": {},
        "trash_candidates": 0,
        "trashed_ok": 0,
        "groups": [],
    }
    trashed_ok = [0]
    trash_ids: set[str] = set()

    if within_folder:
        by_folder: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for av, rows in av_groups.items():
            for row in rows:
                fl = str(row.get(DEDUPE_FOLDER_TAG) or "")
                by_folder.setdefault(fl, {}).setdefault(av, []).append(row)
        for fl, groups in sorted(by_folder.items()):
            for av, rows in sorted(groups.items()):
                if len(rows) < 2:
                    continue
                stats["within_groups"] += 1
                keeper, trash_rows = pick_keeper_and_trash(rows)
                print(f"[within:{fl}] {av} keep {keeper.get('name')!r}")
                stats["trash_candidates"] += len(trash_rows)
                details = _trash_rows(trash_rows, apply=apply, trash_ids=trash_ids, trashed_ok=trashed_ok)
                stats["groups"].append(
                    {"phase": "within", "folder": fl, "av_number": av, "trash": details},
                )

    if cross_folder and len(folders) > 1:
        cross = cross_folder_dup_groups_tiered(av_groups)
        by_keeper: dict[str, int] = {}
        for av, rows in sorted(cross.items()):
            stats["cross_groups"] += 1
            kf, keeper, trash_rows = pick_tiered_cross_folder_keeper_and_trash(
                rows,
                folder_priority=cross_folder_priority,
            )
            by_keeper[kf] = by_keeper.get(kf, 0) + 1
            print(f"[cross] {av} keep in {kf!r} {keeper.get('name')!r}")
            stats["trash_candidates"] += len(trash_rows)
            details = _trash_rows(
                trash_rows,
                apply=apply,
                trash_ids=trash_ids,
                trashed_ok=trashed_ok,
            )
            stats["groups"].append(
                {
                    "phase": "cross",
                    "av_number": av,
                    "keeper_folder": kf,
                    "trash": details,
                },
            )
        stats["cross_groups_by_keeper"] = by_keeper

    stats["trashed_ok"] = trashed_ok[0]
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="GuangYa downloads/JAV JAV dedupe")
    parser.add_argument(
        "--folders",
        default="downloads,JAV,Save",
        help="GuangYa root folders (default: downloads,JAV,Save)",
    )
    parser.add_argument("--apply", action="store_true", help="Delete duplicate files (default: dry-run)")
    parser.add_argument("--skip-within-folder", action="store_true")
    parser.add_argument("--skip-cross-folder", action="store_true")
    parser.add_argument(
        "--cross-priority",
        default="",
        help="Cross-folder keeper priority (default: env GUANGYA_DEDUPE_CROSS_PRIORITY or downloads,Save,JAV)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    folders = parse_folder_list(args.folders)
    if not folders:
        print("[err] empty --folders", file=sys.stderr)
        return 1

    within = within_folder_enabled_from_env() and not args.skip_within_folder
    cross = cross_folder_enabled_from_env() and not args.skip_cross_folder
    cross_priority = (
        parse_folder_list(args.cross_priority)
        if args.cross_priority.strip()
        else cross_folder_priority_from_env()
    )

    try:
        stats = run_dedupe(
            folders=folders,
            apply=args.apply,
            within_folder=within,
            cross_folder=cross,
            cross_folder_priority=cross_priority,
        )
    except Exception as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        print(
            f"[info] mode={stats['mode']} files={stats['files_seen']} "
            f"within_groups={stats['within_groups']} cross_groups={stats['cross_groups']} "
            f"cross_by_keeper={stats.get('cross_groups_by_keeper') or {}} "
            f"trash_candidates={stats['trash_candidates']} trashed_ok={stats['trashed_ok']}",
        )
    from guangya_dedupe_summary import merge_summary

    merge_summary({"dedupe": stats})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
