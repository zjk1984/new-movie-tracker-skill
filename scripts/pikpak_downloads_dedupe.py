#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deduplicate PikPak downloads folder by AV number and domestic/no-av titles.

Phase 1 (JAV): same 番号 groups, keeper UC > C > file size.
Phase 1b (cross-folder): when ``--folders downloads,JAV`` (or PIKPAK_DEDUPE_FOLDERS),
keep the best copy in ``downloads`` and trash duplicates in other folders (e.g. JAV).
Phase 2 (domestic): completed files without a JAV 番号 (including pseudo-JAV codes
when ``PIKPAK_DEDUPE_PSEUDO_AS_JAV=0``) group by btih in filename, PikPak hash,
or normalized title; keeper is largest size then lexicographic name.
Use ``--skip-domestic`` or ``PIKPAK_DEDUPE_DOMESTIC=0`` to run phase 1 only.
Phase 3 (domestic small): trash completed 国产 files under 30 MiB in
``PIKPAK_DEDUPE_DOMESTIC_FOLDERS`` (default ``My Pack``); ``--skip-domestic-small`` to disable.

Multi-folder: ``--folders downloads,JAV`` or env ``PIKPAK_DEDUPE_FOLDERS=downloads,JAV``.
Cross-folder policy: same 番号 in downloads and JAV → keep best in downloads (UC > C > size).
``PIKPAK_DEDUPE_WITHIN_FOLDER=0`` / ``--skip-within-folder`` skips per-folder JAV dedupe.
``PIKPAK_DEDUPE_CROSS_FOLDER=0`` / ``--skip-cross-folder`` skips cross-folder phase.
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
    DEDUPE_FOLDER_TAG,
    DOWNLOADS_KEEPER_FOLDER,
    classify_filename_variant,
    collect_domestic_small_trash_candidates,
    cross_folder_dup_groups,
    cross_folder_enabled_from_env,
    domestic_small_enabled_from_env,
    domestic_small_folders_from_env,
    domestic_small_min_bytes_from_env,
    file_row_size_bytes,
    folders_from_env,
    group_files_by_av_number,
    group_files_domestic,
    group_tagged_files_by_av_number,
    parse_folder_list,
    pick_cross_folder_keeper_and_trash,
    pick_keeper_and_trash,
    pick_keeper_and_trash_domestic,
    pseudo_as_jav_from_env,
    tag_row_folder,
    within_folder_enabled_from_env,
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


def jav_low_score_enabled_from_env() -> bool:
    return os.environ.get("PIKPAK_JAV_LOW_SCORE", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _resolve_folders(
    folder: str,
    folders_arg: str | None,
) -> list[str]:
    if folders_arg and folders_arg.strip():
        parsed = parse_folder_list(folders_arg)
        if not parsed:
            raise ValueError("empty --folders list")
        return parsed
    env_folders = folders_from_env()
    if env_folders:
        return env_folders
    return [folder or DEFAULT_FOLDER]


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
    trash_ids: set[str],
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
        if apply and fid and fid not in trash_ids:
            try:
                trash_file(session, token, device_id, user_id, fid)
                trashed_ok_counter[0] += 1
                trash_ids.add(str(fid))
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


def _process_cross_folder_group(
    av: str,
    rows: list[dict[str, Any]],
    *,
    apply: bool,
    session: Any,
    token: str,
    device_id: str,
    user_id: str,
    trashed_ok_counter: list[int],
    trash_ids: set[str],
    keeper_folder: str = DOWNLOADS_KEEPER_FOLDER,
) -> dict[str, Any]:
    from pikpak_download import trash_file

    keeper, trash_rows = pick_cross_folder_keeper_and_trash(rows, keeper_folder=keeper_folder)
    k_name = keeper.get("name", "")
    k_rank = classify_filename_variant(k_name)
    k_size = int(keeper.get("size") or 0)
    k_folder = str(keeper.get(DEDUPE_FOLDER_TAG) or keeper_folder)
    print(
        f"[cross] {av} keep in {k_folder!r} rank={k_rank} size={k_size} {k_name!r}",
    )

    trash_details: list[dict[str, Any]] = []
    for row in trash_rows:
        t_name = row.get("name", "")
        t_rank = classify_filename_variant(t_name)
        t_size = int(row.get("size") or 0)
        t_folder = str(row.get(DEDUPE_FOLDER_TAG) or "?")
        fid = row.get("id", "")
        action = "trash" if apply else "would-trash"
        print(
            f"  [{action}] from={t_folder!r} rank={t_rank} size={t_size} "
            f"{t_name!r} id={fid}",
        )
        trashed = False
        if apply and fid and fid not in trash_ids:
            try:
                trash_file(session, token, device_id, user_id, fid)
                trashed_ok_counter[0] += 1
                trash_ids.add(str(fid))
                trashed = True
            except Exception as exc:
                print(f"  [err] trash failed {t_name!r}: {exc}", file=sys.stderr)
        trash_details.append(
            {
                "name": t_name,
                "size": t_size,
                "variant_rank": t_rank,
                "folder": t_folder,
                "id": fid,
                "trashed_ok": trashed if apply else None,
            },
        )

    return {
        "av_number": av,
        "keeper_folder": k_folder,
        "keeper": {
            "name": k_name,
            "size": k_size,
            "variant_rank": k_rank,
            "folder": k_folder,
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
    trash_ids: set[str],
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
        if apply and fid and fid not in trash_ids:
            try:
                trash_file(session, token, device_id, user_id, fid)
                trashed_ok_counter[0] += 1
                trash_ids.add(str(fid))
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


def _process_domestic_small_trash(
    rows: list[dict[str, Any]],
    *,
    apply: bool,
    session: Any,
    token: str,
    device_id: str,
    user_id: str,
    trashed_ok_counter: list[int],
    trash_ids: set[str],
    min_bytes: int,
) -> list[dict[str, Any]]:
    from pikpak_download import trash_file

    report_rows: list[dict[str, Any]] = []
    for row in rows:
        t_name = row.get("name", "")
        t_size = file_row_size_bytes(row) or 0
        t_folder = str(row.get(DEDUPE_FOLDER_TAG) or "")
        fid = row.get("id", "")
        action = "trash" if apply else "would-trash"
        folder_note = f" folder={t_folder!r}" if t_folder else ""
        print(
            f"  [domestic_small {action}] size={t_size} (<{min_bytes}) "
            f"{t_name!r}{folder_note} id={fid}",
        )
        trashed = False
        if apply and fid and fid not in trash_ids:
            try:
                trash_file(session, token, device_id, user_id, fid)
                trashed_ok_counter[0] += 1
                trash_ids.add(str(fid))
                trashed = True
            except Exception as exc:
                print(f"  [err] trash failed {t_name!r}: {exc}", file=sys.stderr)
        report_rows.append(
            {
                "name": t_name,
                "size": t_size,
                "folder": t_folder,
                "id": fid,
                "min_bytes": min_bytes,
                "trashed_ok": trashed if apply else None,
            },
        )
    return report_rows


def run_dedupe(
    *,
    folder: str = DEFAULT_FOLDER,
    folders: list[str] | None = None,
    parent_id: str | None = None,
    apply: bool = False,
    access_token: str | None = None,
    push_report: bool = True,
    skip_domestic: bool = False,
    skip_domestic_small: bool = False,
    skip_within_folder: bool = False,
    skip_cross_folder: bool = False,
    skip_jav_low_score: bool = False,
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

    folder_list = folders if folders is not None else _resolve_folders(folder, None)
    multi_folder = len(folder_list) > 1
    run_within = not skip_within_folder and within_folder_enabled_from_env()
    run_cross = multi_folder and not skip_cross_folder and cross_folder_enabled_from_env()
    run_domestic = not skip_domestic and domestic_enabled_from_env()
    run_domestic_small = not skip_domestic_small and domestic_small_enabled_from_env()
    pseudo_jav = pseudo_as_jav_from_env(None)
    domestic_small_min_bytes = domestic_small_min_bytes_from_env()
    domestic_small_folder_list = domestic_small_folders_from_env() if run_domestic_small else []

    folder_entries: dict[str, list[dict[str, Any]]] = {}
    folder_parent_ids: dict[str, str] = {}
    for folder_name in folder_list:
        parent_override = parent_id if len(folder_list) == 1 else None
        try:
            resolved_parent = resolve_parent_id(
                session,
                token,
                device_id,
                user_id,
                folder=folder_name,
                parent_override=parent_override,
            )
        except RuntimeError as exc:
            print(f"[err] {exc}", file=sys.stderr)
            return 1
        folder_parent_ids[folder_name] = resolved_parent
        folder_entries[folder_name] = list_all_files(
            session, token, device_id, user_id, parent_id=resolved_parent,
        )

    if run_domestic_small:
        for folder_name in domestic_small_folder_list:
            if folder_name in folder_entries:
                continue
            try:
                resolved_parent = resolve_parent_id(
                    session,
                    token,
                    device_id,
                    user_id,
                    folder=folder_name,
                    parent_override=None,
                )
            except RuntimeError as exc:
                print(f"[err] domestic_small folder {exc}", file=sys.stderr)
                return 1
            folder_parent_ids[folder_name] = resolved_parent
            folder_entries[folder_name] = list_all_files(
                session, token, device_id, user_id, parent_id=resolved_parent,
            )

    folder_desc = ",".join(folder_list)
    parent_desc = (
        folder_parent_ids.get(folder_list[0], "")
        if len(folder_list) == 1
        else "; ".join(f"{n}={folder_parent_ids[n]}" for n in folder_list)
    )

    print(
        f"[info] folders={folder_desc!r} mode={'apply' if apply else 'dry-run'} "
        f"pseudo_as_jav={pseudo_jav} within_folder={'on' if run_within else 'off'} "
        f"cross_folder={'on' if run_cross else 'off'} domestic={'on' if run_domestic else 'off'} "
        f"domestic_small={'on' if run_domestic_small else 'off'}",
    )
    if run_domestic_small:
        print(
            f"[info] domestic_small folders={','.join(domestic_small_folder_list)!r} "
            f"min_bytes={domestic_small_min_bytes} "
            f"(~{domestic_small_min_bytes / (1024 * 1024):.0f} MiB)",
        )

    all_tagged: list[dict[str, Any]] = []
    total_files = 0
    for folder_name, entries in folder_entries.items():
        total_files += len(entries)
        for row in entries:
            all_tagged.append(tag_row_folder(row, folder_name))

    combined_groups, combined_skipped = group_tagged_files_by_av_number(
        all_tagged,
        pseudo_as_jav=pseudo_jav,
    )
    cross_groups = (
        cross_folder_dup_groups(combined_groups, keeper_folder=DOWNLOADS_KEEPER_FOLDER)
        if run_cross
        else {}
    )
    cross_avs = set(cross_groups)

    report_groups: list[dict[str, Any]] = []
    cross_report_groups: list[dict[str, Any]] = []
    domestic_report_groups: list[dict[str, Any]] = []
    domestic_small_report_rows: list[dict[str, Any]] = []
    trash_total = 0
    cross_trash_total = 0
    domestic_trash_total = 0
    trashed_ok_counter = [0]
    trash_ids: set[str] = set()

    dup_groups_count = 0
    av_groups_count = 0
    skipped_no_av = 0

    if run_within:
        for folder_name in folder_list:
            entries = folder_entries[folder_name]
            groups, folder_skipped = group_files_by_av_number(entries, pseudo_as_jav=pseudo_jav)
            skipped_no_av += folder_skipped
            if not multi_folder:
                av_groups_count = len(groups)
            dup_groups = {av: rows for av, rows in groups.items() if len(rows) >= 2}
            if multi_folder:
                if folder_name != DOWNLOADS_KEEPER_FOLDER:
                    dup_groups = {
                        av: rows for av, rows in dup_groups.items() if av not in cross_avs
                    }
            dup_groups_count += len(dup_groups)
            print(
                f"[info] folder={folder_name!r} files={len(entries)} av_groups={len(groups)} "
                f"duplicate_groups={len(dup_groups)} skipped_no_av={skipped_no_av}",
            )
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
                            trash_ids=trash_ids,
                        ),
                    )
            else:
                print(f"[info] nothing to dedupe (JAV within {folder_name!r})")
    else:
        print("[info] within-folder JAV dedupe skipped")

    if multi_folder:
        av_groups_count = len(combined_groups)
        if not run_within:
            skipped_no_av = combined_skipped

    if run_cross and cross_groups:
        print(
            f"[info] cross_folder duplicate_groups={len(cross_groups)} "
            f"(keeper folder={DOWNLOADS_KEEPER_FOLDER!r})",
        )
        for av in sorted(cross_groups):
            rows = cross_groups[av]
            cross_trash_total += len(rows) - 1
            cross_report_groups.append(
                _process_cross_folder_group(
                    av,
                    rows,
                    apply=apply,
                    session=session,
                    token=token,
                    device_id=device_id,
                    user_id=user_id,
                    trashed_ok_counter=trashed_ok_counter,
                    trash_ids=trash_ids,
                ),
            )
    elif run_cross:
        print("[info] nothing to dedupe (cross-folder)")

    domestic_candidates = 0
    if run_domestic:
        for folder_name in folder_list:
            entries = folder_entries[folder_name]
            domestic_groups, folder_domestic_candidates = group_files_domestic(
                entries,
                pseudo_as_jav=pseudo_jav,
            )
            domestic_candidates += folder_domestic_candidates
            folder_domestic_dup = {
                k: rows for k, rows in domestic_groups.items() if len(rows) >= 2
            }
            print(
                f"[info] folder={folder_name!r} domestic_candidates={folder_domestic_candidates} "
                f"domestic_duplicate_groups={len(folder_domestic_dup)}",
            )
            if folder_domestic_dup:
                for group_key in sorted(folder_domestic_dup):
                    rows = folder_domestic_dup[group_key]
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
                            trash_ids=trash_ids,
                        ),
                    )
        if not domestic_report_groups:
            print("[info] nothing to dedupe (domestic)")
    else:
        print("[info] domestic dedupe skipped")

    domestic_small_trash_total = 0
    if run_domestic_small:
        all_small_candidates: list[dict[str, Any]] = []
        for folder_name in domestic_small_folder_list:
            entries = folder_entries.get(folder_name, [])
            candidates, size_missing = collect_domestic_small_trash_candidates(
                entries,
                min_bytes=domestic_small_min_bytes,
                pseudo_as_jav=pseudo_jav,
            )
            for row in size_missing:
                name = str(row.get("name") or "")
                print(
                    f"[warn] domestic_small skip size missing/0: folder={folder_name!r} {name!r}",
                    file=sys.stderr,
                )
            tagged = [tag_row_folder(r, folder_name) for r in candidates]
            all_small_candidates.extend(tagged)
        domestic_small_trash_total = len(all_small_candidates)
        print(f"[info] domestic_small_trash_candidates={domestic_small_trash_total}")
        if all_small_candidates:
            domestic_small_report_rows = _process_domestic_small_trash(
                all_small_candidates,
                apply=apply,
                session=session,
                token=token,
                device_id=device_id,
                user_id=user_id,
                trashed_ok_counter=trashed_ok_counter,
                trash_ids=trash_ids,
                min_bytes=domestic_small_min_bytes,
            )
        else:
            print("[info] nothing to trash (domestic_small)")
    else:
        print("[info] domestic small-file purge skipped")

    trashed_ok = trashed_ok_counter[0]
    stats = {
        "total_files": total_files,
        "av_groups": av_groups_count,
        "duplicate_groups": dup_groups_count if run_within else 0,
        "skipped_no_av": skipped_no_av,
        "trash_candidates": trash_total,
        "cross_folder_duplicate_groups": len(cross_groups) if run_cross else 0,
        "cross_folder_trash_candidates": cross_trash_total,
        "domestic_candidates": domestic_candidates if run_domestic else 0,
        "domestic_duplicate_groups": len(domestic_report_groups),
        "domestic_trash_candidates": domestic_trash_total,
        "domestic_small_trash_candidates": domestic_small_trash_total if run_domestic_small else 0,
        "domestic_small_min_bytes": domestic_small_min_bytes if run_domestic_small else 0,
        "domestic_small_folders": domestic_small_folder_list if run_domestic_small else [],
        "trashed_ok": trashed_ok if apply else 0,
        "folders": folder_list,
    }

    print(
        f"[summary] within_duplicate_groups={dup_groups_count} within_trash={trash_total} "
        f"cross_duplicate_groups={len(cross_groups) if run_cross else 0} "
        f"cross_trash={cross_trash_total} "
        f"domestic_duplicate_groups={len(domestic_report_groups)} "
        f"domestic_trash={domestic_trash_total} "
        f"domestic_small_trash={domestic_small_trash_total} "
        f"trashed={trashed_ok if apply else 0}",
    )

    jav_low_score_stats: dict[str, Any] | None = None
    jav_low_score_rows: list[dict[str, Any]] | None = None
    jav_low_score_max: float | None = None
    jav_low_score_report_path: Path | None = None
    jav_low_score_archived: list[Path] = []

    run_jav_low = not skip_jav_low_score and jav_low_score_enabled_from_env()
    if run_jav_low:
        from pikpak_jav_low_score_report import (
            _resolve_jav_folder_name,
            run_jav_low_score_report,
        )

        jav_folder_name = _resolve_jav_folder_name(None, folder_list)
        if jav_folder_name and jav_folder_name in folder_entries:
            try:
                low_result = run_jav_low_score_report(
                    folder=jav_folder_name,
                    folder_list=folder_list,
                    entries=folder_entries[jav_folder_name],
                    resolved_parent=folder_parent_ids.get(jav_folder_name),
                    push_report=False,
                    write_standalone=True,
                )
                jav_low_score_stats = low_result.get("stats")
                jav_low_score_rows = low_result.get("rows")
                jav_low_score_max = low_result.get("max_score_exclusive")
                rp = low_result.get("report_path")
                if rp is not None:
                    jav_low_score_report_path = Path(rp)
                jav_low_score_archived = list(low_result.get("archived_paths") or [])
            except RuntimeError as exc:
                print(f"[warn] jav_low_score skipped: {exc}")
        else:
            print("[info] jav_low_score skipped (JAV folder not in scan set)")

    from run_report import write_pikpak_dedupe_report

    report_result = write_pikpak_dedupe_report(
        folder=folder_desc,
        parent_id=parent_desc if parent_desc else None,
        apply=apply,
        stats=stats,
        groups=report_groups,
        cross_folder_groups=cross_report_groups,
        domestic_groups=domestic_report_groups,
        domestic_small_trash=domestic_small_report_rows,
        jav_low_score_stats=jav_low_score_stats,
        jav_low_score_rows=jav_low_score_rows,
        jav_low_score_max_exclusive=jav_low_score_max,
    )
    _push_dedupe_report(
        report_result.path,
        push_report=push_report,
        archived_paths=report_result.archived_paths,
    )
    if jav_low_score_report_path is not None:
        _push_dedupe_report(
            jav_low_score_report_path,
            push_report=push_report,
            archived_paths=jav_low_score_archived,
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove duplicate AV/domestic files in PikPak folder(s).",
    )
    parser.add_argument(
        "--folder",
        default=DEFAULT_FOLDER,
        help=f"PikPak folder name when not using --folders (default: {DEFAULT_FOLDER})",
    )
    parser.add_argument(
        "--folders",
        default=None,
        help="Comma-separated folder names for within + cross-folder dedupe "
        "(e.g. downloads,JAV; or set PIKPAK_DEDUPE_FOLDERS)",
    )
    parser.add_argument(
        "--parent",
        default=None,
        help="PikPak folder id override (single --folder only)",
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
        "--skip-domestic-small",
        action="store_true",
        help="Skip trashing completed domestic files under min size in My Pack (etc.)",
    )
    parser.add_argument(
        "--skip-within-folder",
        action="store_true",
        help="Skip per-folder JAV dedupe (cross-folder only when --folders set)",
    )
    parser.add_argument(
        "--skip-cross-folder",
        action="store_true",
        help="Skip cross-folder dedupe (within-folder only)",
    )
    parser.add_argument(
        "--skip-jav-low-score",
        action="store_true",
        help="Skip JAV folder JavDB low-score report (default: on when JAV scanned)",
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

    try:
        folder_list = _resolve_folders(args.folder, args.folders)
    except ValueError as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 1

    return run_dedupe(
        folder=args.folder,
        folders=folder_list,
        parent_id=args.parent,
        apply=apply,
        push_report=push_report,
        skip_domestic=bool(args.skip_domestic),
        skip_domestic_small=bool(args.skip_domestic_small),
        skip_within_folder=bool(args.skip_within_folder),
        skip_cross_folder=bool(args.skip_cross_folder),
        skip_jav_low_score=bool(args.skip_jav_low_score),
    )


if __name__ == "__main__":
    sys.exit(main())
