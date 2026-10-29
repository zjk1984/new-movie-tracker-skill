#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Report JAV-folder 番号 with JavDB score below threshold (default < 4).

Uses the same PikPak listing and 番号 grouping as downloads dedupe (list_all_files on
JAV root only; completed files only). Fetches JavDB metadata via javdb_client (cached).
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
    group_files_by_av_number,
    pseudo_as_jav_from_env,
)
from pikpak_jav_low_score_lib import (  # noqa: E402
    DEFAULT_MAX_SCORE_EXCLUSIVE,
    distinct_av_numbers_from_groups,
    enrich_av_rows_with_javdb,
    filter_and_sort_low_score_rows,
    low_score_stats,
)

def _max_score_exclusive_from_env() -> float:
    raw = os.environ.get("PIKPAK_JAV_LOW_SCORE_MAX", "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return DEFAULT_MAX_SCORE_EXCLUSIVE


def _lookup_delay_seconds() -> float:
    raw = os.environ.get("PIKPAK_JAV_LOW_SCORE_LOOKUP_DELAY", "0.35").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.35


def _push_report(
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


def _resolve_jav_folder_name(folder: str | None, folder_list: list[str] | None) -> str | None:
    from pikpak_auth import resolve_jav_folder

    from pikpak_download import DEFAULT_FOLDER

    jav_name = (folder or resolve_jav_folder()).strip() or DEFAULT_FOLDER
    if folder_list is not None:
        if jav_name in folder_list:
            return jav_name
        for name in folder_list:
            if name.strip().lower() == jav_name.lower():
                return name
        return None
    return jav_name


def analyze_jav_low_score(
    entries: list[dict[str, Any]],
    *,
    max_score_exclusive: float | None = None,
) -> dict[str, Any]:
    """Query JavDB for 番号 in pre-loaded JAV folder entries (no PikPak I/O)."""
    from javdb_client import JavDBClient, build_error_report, build_query_report

    threshold = (
        float(max_score_exclusive)
        if max_score_exclusive is not None
        else _max_score_exclusive_from_env()
    )
    pseudo_jav = pseudo_as_jav_from_env(None)
    groups, skipped = group_files_by_av_number(entries, pseudo_as_jav=pseudo_jav)
    av_numbers = distinct_av_numbers_from_groups(groups)

    client = JavDBClient()
    delay = _lookup_delay_seconds()

    def lookup_fn(av: str) -> dict[str, Any]:
        try:
            info = client.lookup(av, fetch_magnets=False, best_only=False)
            return build_query_report(info)
        except Exception as exc:
            return build_error_report(av, str(exc))

    all_rows = enrich_av_rows_with_javdb(
        av_numbers,
        groups,
        lookup_fn,
        sleep_after_lookup=delay,
    )
    filtered = filter_and_sort_low_score_rows(
        all_rows,
        max_score_exclusive=threshold,
    )
    stats = low_score_stats(
        all_rows,
        filtered,
        av_count=len(av_numbers),
        max_score_exclusive=threshold,
    )
    stats["skipped_no_av"] = skipped
    stats["jav_folder_files"] = len(entries)

    return {
        "stats": stats,
        "rows": filtered,
        "all_rows": all_rows,
        "max_score_exclusive": threshold,
    }


def run_jav_low_score_report(
    *,
    folder: str | None = None,
    parent_id: str | None = None,
    folder_list: list[str] | None = None,
    entries: list[dict[str, Any]] | None = None,
    resolved_parent: str | None = None,
    push_report: bool = True,
    max_score_exclusive: float | None = None,
    write_standalone: bool = True,
) -> dict[str, Any]:
    """List JAV folder (unless entries provided), query JavDB, write report."""
    import requests

    from pikpak_auth import inspect_jwt_token, resolve_token
    from pikpak_download import find_folder_id, list_all_files
    from run_report import write_pikpak_jav_low_score_report

    load_env_local()
    jav_folder = _resolve_jav_folder_name(folder, folder_list)
    if not jav_folder:
        raise RuntimeError("JAV folder not in folder list")

    threshold = (
        float(max_score_exclusive)
        if max_score_exclusive is not None
        else _max_score_exclusive_from_env()
    )

    parent_resolved = resolved_parent
    file_entries = entries

    if file_entries is None:
        token = resolve_token(None)
        if not token:
            raise RuntimeError(
                "no PikPak token: run `python scripts/pikpak_login.py login` or set PIKPAK_TOKEN",
            )

        jwt_info = inspect_jwt_token(token)
        if not jwt_info.get("valid_jwt"):
            raise RuntimeError(f"invalid token: {jwt_info.get('message')}")
        if jwt_info.get("is_expired"):
            raise RuntimeError(f"token expired: {jwt_info.get('message')}")

        payload = jwt_info.get("payload") or {}
        user_id = payload.get("sub", "")
        device_id = hashlib.md5(user_id.encode()).hexdigest()
        session = requests.Session()

        if parent_id and parent_id.strip():
            parent_resolved = parent_id.strip()
        elif not parent_resolved:
            parent_resolved = find_folder_id(
                session, token, device_id, user_id, jav_folder,
            )
            if not parent_resolved:
                raise RuntimeError(f"PikPak folder not found: {jav_folder!r}")

        file_entries = list_all_files(
            session, token, device_id, user_id, parent_id=parent_resolved or "",
        )

    analysis = analyze_jav_low_score(
        file_entries or [],
        max_score_exclusive=threshold,
    )
    stats = analysis["stats"]
    filtered = analysis["rows"]

    print(
        f"[info] jav_low_score folder={jav_folder!r} files={stats.get('jav_folder_files')} "
        f"av_numbers={stats.get('jav_folder_av_count')} "
        f"skipped_no_av={stats.get('skipped_no_av')} threshold<{threshold}",
    )
    print(
        f"[summary] jav_low_score queried={stats['javdb_queried']} "
        f"ok={stats['javdb_ok']} below_{threshold}={stats['low_score_count']}",
    )

    result: dict[str, Any] = {
        **analysis,
        "folder": jav_folder,
        "parent_id": parent_resolved,
    }

    if write_standalone:
        report_result = write_pikpak_jav_low_score_report(
            folder=jav_folder,
            parent_id=parent_resolved,
            stats=stats,
            rows=filtered,
            max_score_exclusive=threshold,
        )
        _push_report(
            report_result.path,
            push_report=push_report,
            archived_paths=report_result.archived_paths,
        )
        result["report_path"] = report_result.path
        result["archived_paths"] = report_result.archived_paths

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List JAV folder 番号 and report JavDB scores below threshold.",
    )
    parser.add_argument(
        "--folder",
        default=None,
        help="PikPak JAV folder name (default: PIKPAK_FOLDER_JAV or My Pack)",
    )
    parser.add_argument(
        "--parent",
        default=None,
        help="PikPak folder id override",
    )
    parser.add_argument(
        "--max-score",
        type=float,
        default=None,
        help=f"Exclusive upper bound (default env or {DEFAULT_MAX_SCORE_EXCLUSIVE})",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Write report locally but do not commit/push to GitHub",
    )
    args = parser.parse_args()

    env_no_push = os.environ.get("PIKPAK_JAV_LOW_SCORE_NO_PUSH", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    push_report = not args.no_push and not env_no_push

    try:
        run_jav_low_score_report(
            folder=args.folder,
            parent_id=args.parent,
            push_report=push_report,
            max_score_exclusive=args.max_score,
        )
    except RuntimeError as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
