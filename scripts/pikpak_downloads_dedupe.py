#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deduplicate PikPak downloads folder by AV number and domestic/no-av titles.

Phase 1 (JAV): same 番号 groups, keeper UC > C > file size.
Phase 2 (domestic): completed files without a JAV 番号 (including pseudo-JAV codes
when ``PIKPAK_DEDUPE_PSEUDO_AS_JAV=0``) group by btih in filename, PikPak hash,
or normalized title; keeper is largest size then lexicographic name.
Use ``--skip-domestic`` or ``PIKPAK_DEDUPE_DOMESTIC=0`` to run phase 1 only.
"""
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
    group_files_domestic,
    pick_keeper_and_trash,
    pick_keeper_and_trash_domestic,
    pseudo_as_jav_from_env,
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


def domestic_enabled_from_env() -> bool:
    return os.environ.get("PIKPAK_DEDUPE_DOMESTIC", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _process_jav_group(
    av: str,
    rows: list[dict[str, Any]],
    *,
    apply: bool,
    session: Any,
    token: str,
    device_id: str,
    user_id: str,
    trashed_ok_counter: list[int],
) -> dict[str, Any]:
    from pikpak_download import trash_file

    keeper, trash_rows = pick_keeper_and_trash(rows)
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
                trashed_ok_counter[0] += 1
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

    return {
        "av_number": av,
        "keeper": {
            "name": k_name,
            "size": k_size,
            "variant_rank": k_rank,
        },
        "trash": trash_details,
    }


def _process_domestic_group(
    group_key: str,
    rows: list[dict[str, Any]],
    *,
    apply: bool,
    session: Any,
    token: str,
    device_id: str,
    user_id: str,
    trashed_ok_counter: list[int],
) -> dict[str, Any]:
    from pikpak_download import trash_file

    keeper, trash_rows = pick_keeper_and_trash_domestic(rows)
    k_name = keeper.get("name", "")
    k_size = int(keeper.get("size") or 0)
    print(f"[domestic_group] {group_key} keep size={k_size} {k_name!r}")

    trash_details: list[dict[str, Any]] = []
    for row in trash_rows:
        t_name = row.get("name", "")
        t_size = int(row.get("size") or 0)
        fid = row.get("id", "")
        action = "trash" if apply else "would-trash"
        print(f"  [{action}] size={t_size} {t_name!r} id={fid}")
        trashed = False
        if apply and fid:
            try:
                trash_file(session, token, device_id, user_id, fid)
                trashed_ok_counter[0] += 1
                trashed = True
            except Exception as exc:
                print(f"  [err] trash failed {t_name!r}: {exc}", file=sys.stderr)
        trash_details.append(
            {
                "name": t_name,
                "size": t_size,
                "variant": "国产",
                "id": fid,
                "trashed_ok": trashed if apply else None,
            },
        )

    return {
        "group_key": group_key,
        "keeper": {
            "name": k_name,
            "size": k_size,
        },
        "trash": trash_details,
    }


def run_dedupe(
    *,
    folder: str = DEFAULT_FOLDER,
    parent_id: str | None = None,
    apply: bool = False,
    access_token: str | None = None,
    push_report: bool = True,
    skip_domestic: bool = False,
) -> int:
    import requests

    from pikpak_auth import inspect_jwt_token, resolve_token
    from pikpak_download import list_all_files

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

    run_domestic = not skip_domestic and domestic_enabled_from_env()
    pseudo_jav = pseudo_as_jav_from_env(None)

    print(
        f"[info] folder={folder!r} parent_id={resolved_parent} mode={'apply' if apply else 'dry-run'} "
        f"pseudo_as_jav={pseudo_jav} domestic={'on' if run_domestic else 'off'}",
    )

    all_entries = list_all_files(session, token, device_id, user_id, parent_id=resolved_parent)
    groups, skipped_no_av = group_files_by_av_number(all_entries, pseudo_as_jav=pseudo_jav)
    dup_groups = {av: rows for av, rows in groups.items() if len(rows) >= 2}

    print(
        f"[info] files={len(all_entries)} av_groups={len(groups)} "
        f"duplicate_groups={len(dup_groups)} skipped_no_av={skipped_no_av}",
    )

    report_groups: list[dict[str, Any]] = []
    domestic_report_groups: list[dict[str, Any]] = []
    trash_total = 0
    domestic_trash_total = 0
    trashed_ok_counter = [0]

    if dup_groups:
        for av in sorted(dup_groups):
            rows = dup_groups[av]
            trash_total += len(rows) - 1
            report_groups.append(
                _process_jav_group(
                    av,
                    rows,
                    apply=apply,
                    session=session,
                    token=token,
                    device_id=device_id,
                    user_id=user_id,
                    trashed_ok_counter=trashed_ok_counter,
                ),
            )
    else:
        print("[info] nothing to dedupe (JAV)")

    domestic_dup_groups: dict[str, list[dict[str, Any]]] = {}
    domestic_candidates = 0
    if run_domestic:
        domestic_groups, domestic_candidates = group_files_domestic(
            all_entries,
            pseudo_as_jav=pseudo_jav,
        )
        domestic_dup_groups = {k: rows for k, rows in domestic_groups.items() if len(rows) >= 2}
        print(
            f"[info] domestic_candidates={domestic_candidates} domestic_groups={len(domestic_groups)} "
            f"domestic_duplicate_groups={len(domestic_dup_groups)}",
        )
        if domestic_dup_groups:
            for group_key in sorted(domestic_dup_groups):
                rows = domestic_dup_groups[group_key]
                domestic_trash_total += len(rows) - 1
                domestic_report_groups.append(
                    _process_domestic_group(
                        group_key,
                        rows,
                        apply=apply,
                        session=session,
                        token=token,
                        device_id=device_id,
                        user_id=user_id,
                        trashed_ok_counter=trashed_ok_counter,
                    ),
                )
        else:
            print("[info] nothing to dedupe (domestic)")

    trashed_ok = trashed_ok_counter[0]
    stats = {
        "total_files": len(all_entries),
        "av_groups": len(groups),
        "duplicate_groups": len(dup_groups),
        "skipped_no_av": skipped_no_av,
        "trash_candidates": trash_total,
        "domestic_candidates": domestic_candidates if run_domestic else 0,
        "domestic_duplicate_groups": len(domestic_dup_groups),
        "domestic_trash_candidates": domestic_trash_total,
        "trashed_ok": trashed_ok if apply else 0,
    }

    print(
        f"[summary] duplicate_groups={len(dup_groups)} trash_candidates={trash_total} "
        f"domestic_duplicate_groups={len(domestic_dup_groups)} "
        f"domestic_trash_candidates={domestic_trash_total} "
        f"trashed={trashed_ok if apply else 0}",
    )

    from run_report import write_pikpak_dedupe_report

    report_result = write_pikpak_dedupe_report(
        folder=folder,
        parent_id=resolved_parent,
        apply=apply,
        stats=stats,
        groups=report_groups,
        domestic_groups=domestic_report_groups,
    )
    _push_dedupe_report(
        report_result.path,
        push_report=push_report,
        archived_paths=report_result.archived_paths,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove duplicate AV/domestic files in a PikPak folder.",
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
        "--skip-domestic",
        action="store_true",
        help="Run JAV 番号 dedupe only (skip domestic/no-av phase)",
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
        skip_domestic=bool(args.skip_domestic),
    )


if __name__ == "__main__":
    sys.exit(main())
