#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deduplicate PikPak downloads folder by AV number (UC > C > size)."""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from env_utils import load_env_local  # noqa: E402
from pikpak_downloads_dedupe_lib import (  # noqa: E402
    DEFAULT_FOLDER,
    classify_filename_variant,
    group_files_by_av_number,
    pick_keeper_and_trash,
)


def resolve_parent_id(
    session: Any,
    token: str,
    device_id: str,
    user_id: str,
    *,
    folder: str,
    parent_override: str | None,
) -> str:
    from pikpak_download import find_folder_id

    if parent_override and parent_override.strip():
        return parent_override.strip()
    parent_id = find_folder_id(session, token, device_id, user_id, folder)
    if not parent_id:
        raise RuntimeError(f"PikPak folder not found: {folder!r}")
    return parent_id


def _push_dedupe_report(
    report_path: Path,
    *,
    push_report: bool,
    archived_paths: list[Path],
) -> None:
    from feishu_notify import _push_report_and_url

    _push_report_and_url(
        report_path,
        push_report=push_report,
        archived_paths=archived_paths,
    )


def run_dedupe(
    *,
    folder: str = DEFAULT_FOLDER,
    parent_id: str | None = None,
    apply: bool = False,
    access_token: str | None = None,
    push_report: bool = True,
) -> int:
    import requests

    from pikpak_auth import inspect_jwt_token, resolve_token
    from pikpak_download import list_all_files, trash_file

    load_env_local()
    token = resolve_token(access_token)
    if not token:
        print(
            "[err] no PikPak token: run `python scripts/pikpak_login.py login` or set PIKPAK_TOKEN",
            file=sys.stderr,
        )
        return 1

    jwt_info = inspect_jwt_token(token)
    if not jwt_info.get("valid_jwt"):
        print(f"[err] invalid token: {jwt_info.get('message')}", file=sys.stderr)
        return 1
    if jwt_info.get("is_expired"):
        print(f"[err] token expired: {jwt_info.get('message')}", file=sys.stderr)
        return 1

    payload = jwt_info.get("payload") or {}
    user_id = payload.get("sub", "")
    device_id = hashlib.md5(user_id.encode()).hexdigest()
    session = requests.Session()

    try:
        resolved_parent = resolve_parent_id(
            session, token, device_id, user_id, folder=folder, parent_override=parent_id,
        )
    except RuntimeError as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 1

    print(f"[info] folder={folder!r} parent_id={resolved_parent} mode={'apply' if apply else 'dry-run'}")

    all_entries = list_all_files(session, token, device_id, user_id, parent_id=resolved_parent)
    groups, skipped_no_av = group_files_by_av_number(all_entries)
    dup_groups = {av: rows for av, rows in groups.items() if len(rows) >= 2}

    print(
        f"[info] files={len(all_entries)} av_groups={len(groups)} "
        f"duplicate_groups={len(dup_groups)} skipped_no_av={skipped_no_av}",
    )

    report_groups: list[dict[str, Any]] = []
    trash_total = 0
    trashed_ok = 0

    if dup_groups:
        for av in sorted(dup_groups):
            rows = dup_groups[av]
            keeper, trash_rows = pick_keeper_and_trash(rows)
            trash_total += len(trash_rows)
            k_name = keeper.get("name", "")
            k_rank = classify_filename_variant(k_name)
            k_size = int(keeper.get("size") or 0)
            print(f"[group] {av} keep rank={k_rank} size={k_size} {k_name!r}")

            trash_details: list[dict[str, Any]] = []
            for row in trash_rows:
                t_name = row.get("name", "")
                t_rank = classify_filename_variant(t_name)
                t_size = int(row.get("size") or 0)
                fid = row.get("id", "")
                action = "trash" if apply else "would-trash"
                print(f"  [{action}] rank={t_rank} size={t_size} {t_name!r} id={fid}")
                trashed = False
                if apply and fid:
                    try:
                        trash_file(session, token, device_id, user_id, fid)
                        trashed_ok += 1
                        trashed = True
                    except Exception as exc:
                        print(f"  [err] trash failed {t_name!r}: {exc}", file=sys.stderr)
                trash_details.append(
                    {
                        "name": t_name,
                        "size": t_size,
                        "variant_rank": t_rank,
                        "id": fid,
                        "trashed_ok": trashed if apply else None,
                    },
                )

            report_groups.append(
                {
                    "av_number": av,
                    "keeper": {
                        "name": k_name,
                        "size": k_size,
                        "variant_rank": k_rank,
                    },
                    "trash": trash_details,
                },
            )
    else:
        print("[info] nothing to dedupe")

    stats = {
        "total_files": len(all_entries),
        "av_groups": len(groups),
        "duplicate_groups": len(dup_groups),
        "skipped_no_av": skipped_no_av,
        "trash_candidates": trash_total,
        "trashed_ok": trashed_ok if apply else 0,
    }

    print(
        f"[summary] duplicate_groups={len(dup_groups)} trash_candidates={trash_total} "
        f"trashed={trashed_ok if apply else 0}",
    )

    from run_report import write_pikpak_dedupe_report

    report_result = write_pikpak_dedupe_report(
        folder=folder,
        parent_id=resolved_parent,
        apply=apply,
        stats=stats,
        groups=report_groups,
    )
    _push_dedupe_report(
        report_result.path,
        push_report=push_report,
        archived_paths=report_result.archived_paths,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove duplicate AV files in a PikPak folder (keep UC > C > larger size).",
    )
    parser.add_argument(
        "--folder",
        default=DEFAULT_FOLDER,
        help=f"PikPak folder name (default: {DEFAULT_FOLDER})",
    )
    parser.add_argument(
        "--parent",
        default=None,
        help="PikPak folder id override (skips folder name lookup)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Move duplicate files to trash (default: dry-run only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=None,
        help="Print actions without trashing (default unless --apply)",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Write report locally but do not commit/push to GitHub",
    )
    args = parser.parse_args()
    apply = bool(args.apply)
    if args.dry_run is not None and args.dry_run and args.apply:
        print("[err] cannot use --dry-run with --apply", file=sys.stderr)
        return 1

    env_no_push = os.environ.get("PIKPAK_DEDUPE_NO_PUSH", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    push_report = not args.no_push and not env_no_push

    return run_dedupe(
        folder=args.folder,
        parent_id=args.parent,
        apply=apply,
        push_report=push_report,
    )


if __name__ == "__main__":
    sys.exit(main())
