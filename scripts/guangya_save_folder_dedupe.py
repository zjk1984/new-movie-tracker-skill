#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dedupe **video** files in GuangYa Save folder by 番号 (keep UC > C > size).

Default: dry-run. ``--apply`` trashes smaller duplicate videos via guangyapan-drive delete_files.
Sidecars / NFO are not deduped here (video-only phase).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from env_utils import SKILL_DIR, load_env_local  # noqa: E402
from guangya_auth import sync_credentials_from_skill_store  # noqa: E402
from guangya_cloud_cli import delete_remote_files, login_status  # noqa: E402
from guangya_save_drive_inventory import (  # noqa: E402
    DEFAULT_SAVE_FOLDER_ID,
    av_from_filename,
    is_video_file,
)
from pikpak_guangya_audit import walk_guangya_files  # noqa: E402
from pikpak_downloads_dedupe_lib import (  # noqa: E402
    pick_keeper_and_trash,
    pseudo_as_jav_from_env,
)

DEFAULT_PARENT = DEFAULT_SAVE_FOLDER_ID


def collect_video_rows(parent_id: str) -> list[dict[str, Any]]:
    pseudo = pseudo_as_jav_from_env(None)
    rows: list[dict[str, Any]] = []
    for row in walk_guangya_files(parent_id):
        if row.get("type") == "directory":
            continue
        if not is_video_file(row):
            continue
        name = str(row.get("name") or "")
        av = av_from_filename(name, pseudo_as_jav=pseudo)
        if not av:
            continue
        tagged = dict(row)
        tagged["av_number"] = av
        rows.append(tagged)
    return rows


def run_save_video_dedupe(*, parent_id: str, apply: bool) -> dict[str, Any]:
    _, payload, _ = login_status()
    if (payload.get("data") or {}).get("logged_in") is not True:
        raise RuntimeError("GuangYa not logged in")

    rows = collect_video_rows(parent_id)
    by_av: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_av.setdefault(str(row["av_number"]), []).append(row)

    dup_groups = {av: files for av, files in by_av.items() if len(files) > 1}
    trash_rows: list[dict[str, Any]] = []
    keep_rows: list[dict[str, Any]] = []
    for av, files in sorted(dup_groups.items()):
        keeper, trash = pick_keeper_and_trash(files)
        keep_rows.append(keeper)
        trash_rows.extend(trash)
        print(f"[dup] {av} keep={keeper.get('name')!r} trash={len(trash)}")

    stats: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run",
        "parent_id": parent_id,
        "video_files": len(rows),
        "unique_av_with_video": len(by_av),
        "dup_av_groups": len(dup_groups),
        "files_to_trash": len(trash_rows),
    }

    if apply and trash_rows:
        ids = [str(r.get("id") or "") for r in trash_rows if r.get("id")]
        if ids:
            result = delete_remote_files(ids)
            stats["delete_result"] = result
            stats["deleted"] = int(result.get("deleted") or 0)
    elif trash_rows:
        for row in trash_rows[:20]:
            print(f"  [would-trash] {row.get('name')!r} id={row.get('id')}")
        if len(trash_rows) > 20:
            print(f"  … and {len(trash_rows) - 20} more")

    return stats


def main() -> int:
    load_env_local()
    parser = argparse.ArgumentParser(description="Dedupe Save folder videos by 番号")
    parser.add_argument("--parent-id", default=DEFAULT_PARENT)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--no-auth-sync", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not args.no_auth_sync:
        sync_credentials_from_skill_store(force=True)

    try:
        stats = run_save_video_dedupe(parent_id=str(args.parent_id).strip(), apply=args.apply)
    except Exception as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        print(
            f"[info] mode={stats['mode']} dup_av={stats['dup_av_groups']} "
            f"trash_files={stats['files_to_trash']} videos={stats['video_files']}",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
