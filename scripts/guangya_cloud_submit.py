#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PikPak ``downloads`` 番号 → JavDB magnet fallback → GuangYa cloud add (Skill CLI).

Environment (also loaded from repo ``.env.local`` when unset):

- ``PIKPAK_TOKEN`` / PikPak login — list PikPak ``downloads`` folder.
- ``PIKPAK_FOLDER_DOWNLOADS`` or ``PIKPAK_DOWNLOADS_FOLDER`` — PikPak folder name
  (default: ``downloads``).
- ``GUANGYAPAN_SKILL_ROOT`` — Skill package root (default:
  ``/cursor/stores/user/skills/guangyapan-drive``).
- ``GUANGYAPAN_PROFILE_DIR`` — agent profile dir (default:
  ``/cursor/stores/user/guangyapan-cursor-profile``).
- ``GUANGYAPAN_AGENT_NAME`` — CLI ``--agent-name`` (default: ``Cursor``).
- ``GUANGYAPAN_DRIVE_LOGIN_MODE`` — set to ``device`` for headless QR login on cloud VMs.
- ``GUANGYAPAN_FOLDER_DOWNLOADS`` — GuangYa target folder at drive root (default: ``downloads``).
- ``RESULT_JSON`` — optional scan ``last_result.json`` for forum link resolution before JavDB.

State: ``data/guangya_submit_state.json`` dedupes by 番号 and URI/btih.
Optional folder id cache: ``data/guangya_downloads_folder_id.json``.

**Policy gate:** JavDB score / region / ``is_submit_eligible`` skips are **disabled by default**
for this PikPak → GuangYa path (dedupe + valid magnet/ed2k/http parsing still apply). Use
``--policy-gate`` to restore submit-style skipping. When scan/JavDB cannot resolve a link,
the script falls back to PikPak ``GET /drive/v1/files/{id}`` (``params.url`` / task URL).

Examples::

  python3 scripts/guangya_cloud_submit.py --limit 5
  python3 scripts/guangya_cloud_submit.py --numbers SSIS-001 IPX-100 --apply
  python3 scripts/guangya_cloud_submit.py --scan-result scan-today/last_result.json --preflight
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from env_utils import SKILL_DIR, load_env_local  # noqa: E402
from guangya_cloud_submit_lib import (  # noqa: E402
    DEFAULT_STATE_PATH,
    enumerate_av_entries_from_files,
    guangya_folder_from_env,
    load_matched_by_av,
    load_submit_state,
    mark_state_submitted,
    resolve_guangya_parent_id,
    resolve_submit_row_for_av,
    resolve_submit_row_from_pikpak_file,
    save_submit_state,
    state_has_submission,
    submit_rows_to_guangya,
)
from javdb_client import JavDBClient  # noqa: E402
from pikpak_downloads_jav_scrape_lib import downloads_folder_from_env  # noqa: E402


def _resolve_pikpak_session():
    import requests

    from pikpak_auth import inspect_jwt_token, resolve_token
    from pikpak_download import find_folder_id, list_all_children

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
    return session, token, device_id, user_id, list_all_children, find_folder_id


def run_pipeline(
    *,
    apply: bool,
    limit: int,
    numbers_filter: set[str] | None,
    pikpak_folder: str,
    guangya_folder: str,
    recursive: bool,
    pikpak_parent_override: str | None,
    scan_path: Path | None,
    state_path: Path,
    preflight: bool,
    apply_policy_gate: bool,
    region_filter: bool,
    javdb_score_gate: bool,
    skip_state: bool,
) -> dict[str, Any]:
    session, token, device_id, user_id, list_all_children, find_folder_id = _resolve_pikpak_session()

    if pikpak_parent_override:
        downloads_parent = pikpak_parent_override.strip()
    else:
        downloads_parent = find_folder_id(session, token, device_id, user_id, pikpak_folder)
        if not downloads_parent:
            raise RuntimeError(f"PikPak folder not found: {pikpak_folder!r}")

    files: list[dict[str, Any]] = []
    if recursive:
        files = list_all_children(
            session,
            token,
            device_id,
            user_id,
            parent_id=downloads_parent,
            complete_files_only=True,
        )
    else:
        from pikpak_download import list_files

        files = list_files(session, token, device_id, user_id, parent_id=downloads_parent)

    av_entries = enumerate_av_entries_from_files(files)
    if numbers_filter:
        av_entries = {k: v for k, v in av_entries.items() if k in numbers_filter}

    matched_by_av = load_matched_by_av(scan_path)
    state = load_submit_state(state_path) if not skip_state else load_submit_state(Path("/dev/null"))
    client = JavDBClient(use_saved_token=True) if apply_policy_gate else None

    stats: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run",
        "pikpak_folder": pikpak_folder,
        "guangya_folder": guangya_folder,
        "pikpak_parent_id": downloads_parent,
        "apply_policy_gate": apply_policy_gate,
        "av_numbers_seen": len(av_entries),
        "planned": 0,
        "skipped_state": 0,
        "skipped_no_link": 0,
        "skipped_gate": 0,
        "submitted": 0,
        "items": [],
    }

    pending_rows: list[dict[str, Any]] = []
    processed = 0

    for av in sorted(av_entries.keys()):
        entry = av_entries[av]
        rep_name = entry.get("name") or av
        file_id = entry.get("file_id") or ""
        if not skip_state and state_has_submission(state, av, ""):
            stats["skipped_state"] += 1
            stats["items"].append({
                "av_number": av,
                "status": "skipped_state",
                "representative_file": rep_name,
            })
            processed += 1
            if limit > 0 and processed >= limit:
                break
            continue

        row, skip_reason, link_source = resolve_submit_row_for_av(
            av,
            representative_name=rep_name,
            scan_item=matched_by_av.get(av),
            javdb_client=client,
            apply_policy_gate=apply_policy_gate,
            region_filter=region_filter,
            javdb_score_gate=javdb_score_gate,
        )
        if not row and file_id:
            row, skip_reason, link_source = resolve_submit_row_from_pikpak_file(
                session,
                token,
                device_id,
                user_id,
                file_id=file_id,
                av_number=av,
                representative_name=rep_name,
            )
        if not row:
            if apply_policy_gate and skip_reason and (
                "javdb" in skip_reason or skip_reason.endswith("_gate")
            ):
                stats["skipped_gate"] += 1
            else:
                stats["skipped_no_link"] += 1
            stats["items"].append({
                "av_number": av,
                "status": "skipped",
                "skip_reason": skip_reason,
                "link_source": link_source,
                "representative_file": rep_name,
            })
            processed += 1
            if limit > 0 and processed >= limit:
                break
            continue

        uri = row.get("uri") or ""
        if not skip_state and state_has_submission(state, av, uri):
            stats["skipped_state"] += 1
            stats["items"].append({
                "av_number": av,
                "status": "skipped_state",
                "uri": uri,
                "representative_file": rep_name,
            })
            processed += 1
            if limit > 0 and processed >= limit:
                break
            continue

        stats["planned"] += 1
        item_out = {
            "av_number": av,
            "status": "planned",
            "uri": uri,
            "link_source": link_source,
            "source": row.get("source"),
            "representative_file": rep_name,
        }
        stats["items"].append(item_out)
        pending_rows.append(row)

        print(
            f"[plan] {av} ← {link_source} {uri[:72]}{'…' if len(uri) > 72 else ''}",
        )
        processed += 1
        if limit > 0 and processed >= limit:
            break

    if apply and pending_rows:
        remote_parent_id = resolve_guangya_parent_id(guangya_folder, create_if_missing=False)
        submit_result = submit_rows_to_guangya(
            pending_rows,
            remote_parent_id=remote_parent_id,
            preflight=preflight,
        )
        stats["guangya"] = submit_result
        stats["submitted"] = submit_result.get("submitted", 0)
        for res in submit_result.get("results") or []:
            av = res.get("av_number") or ""
            uri = res.get("uri") or ""
            task_id = res.get("task_id") or ""
            print(f"[ok] {av} task={task_id or '?'}")
            if not skip_state and uri:
                mark_state_submitted(state, str(av), str(uri), task_id=task_id or None)
        if not skip_state:
            save_submit_state(state_path, state)

    return stats


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    load_env_local()
    parser = argparse.ArgumentParser(
        description="PikPak downloads 番号 → JavDB → GuangYa cloud add (Skill CLI)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Submit cloud_collection_add via GuangYa Skill CLI (default: dry-run)",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max 番号 to process (0=all)")
    parser.add_argument(
        "--numbers",
        default="",
        help="Comma-separated 番号 filter (e.g. SSIS-001,IPX-100)",
    )
    parser.add_argument(
        "--folder",
        default=None,
        help="PikPak folder name (default: PIKPAK_FOLDER_DOWNLOADS / downloads)",
    )
    parser.add_argument(
        "--guangya-folder",
        default=None,
        help="GuangYa root folder name (default: downloads)",
    )
    parser.add_argument("--parent-id", default=None, help="PikPak downloads folder id")
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Only list direct children of PikPak downloads folder",
    )
    parser.add_argument(
        "--scan-result",
        default=os.environ.get("RESULT_JSON", ""),
        help="Optional last_result.json for forum magnets before JavDB fallback",
    )
    parser.add_argument(
        "--state-file",
        default=str(DEFAULT_STATE_PATH),
        help="Dedupe state JSON path",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Include resolve_cloud_collection before each cloud_collection_add",
    )
    parser.add_argument(
        "--policy-gate",
        action="store_true",
        help=(
            "Enable region filter + JavDB is_submit_eligible gate (default: off for PikPak→GuangYa)"
        ),
    )
    parser.add_argument(
        "--no-region-filter",
        action="store_true",
        help="When --policy-gate: disable content region filter",
    )
    parser.add_argument(
        "--no-javdb-score-gate",
        action="store_true",
        help="When --policy-gate: disable JavDB score gate only",
    )
    parser.add_argument(
        "--ignore-state",
        action="store_true",
        help="Do not read/write submit state (still prints plan)",
    )
    parser.add_argument("--json", action="store_true", help="Print stats JSON on stdout")
    args = parser.parse_args()

    pikpak_folder = (args.folder or downloads_folder_from_env()).strip()
    guangya_folder = (args.guangya_folder or guangya_folder_from_env()).strip()
    numbers_filter = None
    if args.numbers.strip():
        numbers_filter = {n.strip().upper() for n in args.numbers.split(",") if n.strip()}

    scan_path = Path(args.scan_result) if args.scan_result.strip() else None
    state_path = Path(args.state_file)

    try:
        stats = run_pipeline(
            apply=args.apply,
            limit=args.limit,
            numbers_filter=numbers_filter,
            pikpak_folder=pikpak_folder,
            guangya_folder=guangya_folder,
            recursive=not args.no_recursive,
            pikpak_parent_override=args.parent_id,
            scan_path=scan_path,
            state_path=state_path,
            preflight=args.preflight,
            apply_policy_gate=args.policy_gate,
            region_filter=not args.no_region_filter,
            javdb_score_gate=not args.no_javdb_score_gate,
            skip_state=args.ignore_state,
        )
    except Exception as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        print(
            f"[info] mode={stats['mode']} av_seen={stats['av_numbers_seen']} "
            f"planned={stats['planned']} skipped_state={stats['skipped_state']} "
            f"skipped_gate={stats['skipped_gate']} skipped_no_link={stats['skipped_no_link']} "
            f"submitted={stats['submitted']}",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
