#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Submit GuangYa Save NFO report magnets to folder **Save** (batched cloud add).

Reads ``reports/guangya_save_nfo_links_*.json`` (``entries`` or ``records``), builds a queue
with **at most one magnet per 番号** (first link in report order for that av), skips 番号
already in ``data/guangya_save_links_download_state.json``, and submits up to ``--limit``
(default 500 **番号** per run) via guangyapan-drive Skill CLI.

Target folder defaults to report ``guangya_folder_id`` (Save ``1963910467505319951``).

Examples::

  python3 scripts/guangya_save_links_download.py --limit 10
  python3 scripts/guangya_save_links_download.py --apply --limit 500 --day 1
  python3 scripts/guangya_save_links_download.py --apply --limit 500 --day 2 \\
    --report reports/guangya_save_nfo_links_2026-11-01.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from download_state import extract_btih, item_download_key  # noqa: E402
from env_utils import SKILL_DIR, beijing_now_iso, load_env_local  # noqa: E402
from guangya_auth import sync_credentials_from_skill_store  # noqa: E402
from guangya_cloud_cli import login_status  # noqa: E402
from guangya_save_magnet_pick import pick_best_magnet_uri  # noqa: E402
from jellyfin_nfo import canonical_av_number  # noqa: E402

_SUPPORTED_URI_PREFIXES = (
    "magnet:",
    "ed2k:",
    "ed2k://",
    "http://",
    "https://",
    "ftp://",
    "thunder://",
)


def uri_supported_by_guangya(uri: str) -> bool:
    u = (uri or "").strip().lower()
    return any(u.startswith(p) for p in _SUPPORTED_URI_PREFIXES)


def _cloud_submit_batch_size() -> int:
    from guangya_cloud_submit_lib import cloud_submit_batch_size

    return cloud_submit_batch_size()


def _submit_rows_to_guangya(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from guangya_cloud_submit_lib import submit_rows_to_guangya

    return submit_rows_to_guangya(*args, **kwargs)

DEFAULT_REPORT_PATH = SKILL_DIR / "reports" / "guangya_save_nfo_links_2026-11-01.json"
DEFAULT_STATE_PATH = SKILL_DIR / "data" / "guangya_save_links_download_state.json"
DEFAULT_ALREADY_ON_DRIVE_PATH = SKILL_DIR / "data" / "guangya_save_already_on_drive.json"
DEFAULT_SAVE_FOLDER_ID = "1963910467505319951"
DEFAULT_BATCH_DELAY_SEC = 1.5
STATE_SCHEMA_VERSION = 2


def empty_state() -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "queue_mode": "one_magnet_per_av",
        "report_path": None,
        "report_generated_at_utc": None,
        "remote_parent_id": DEFAULT_SAVE_FOLDER_ID,
        "queue_av_count": 0,
        "next_queue_index": 0,
        "av_numbers": {},
        "already_in_save_av": [],
        "uris": {},
        "days": {},
        "last_run_utc": None,
    }


def migrate_state(data: dict[str, Any]) -> dict[str, Any]:
    """v1 (per-magnet queue) → v2 (one magnet per 番号). Safe reset when nothing submitted."""
    version = int(data.get("schema_version") or 1)
    if version >= STATE_SCHEMA_VERSION:
        return data
    uris = data.get("uris") or {}
    av_done = data.get("av_numbers") or {}
    if not uris and not av_done:
        data["next_queue_index"] = 0
        data["migration_note"] = (
            "reset next_queue_index: schema v1 magnet-index cursor incompatible with v2 av queue"
        )
    data["schema_version"] = STATE_SCHEMA_VERSION
    data["queue_mode"] = "one_magnet_per_av"
    if "queue_unique_count" in data and "queue_av_count" not in data:
        data.pop("queue_unique_count", None)
    return data


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_state()
    if not isinstance(data, dict):
        return empty_state()
    data.setdefault("uris", {})
    data.setdefault("av_numbers", {})
    data.setdefault("days", {})
    data.setdefault("remote_parent_id", DEFAULT_SAVE_FOLDER_ID)
    data.setdefault("next_queue_index", 0)
    data.setdefault("already_in_save_av", [])
    return migrate_state(data)


def load_already_on_save_avs(
    *,
    state: dict[str, Any] | None = None,
    merge_path: Path | None = None,
) -> set[str]:
    """番号 already on Save (inventory file + state + submitted av_numbers)."""
    found: set[str] = set()
    path = merge_path or DEFAULT_ALREADY_ON_DRIVE_PATH
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            for av in payload.get("av_numbers") or []:
                key = canonical_av_number(str(av))
                if key:
                    found.add(key)
        except (OSError, json.JSONDecodeError):
            pass
    if state:
        for av in (state.get("av_numbers") or {}).keys():
            key = canonical_av_number(str(av))
            if key:
                found.add(key)
    return found


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def state_has_av(state: dict[str, Any], av_number: str) -> bool:
    av = (av_number or "").strip().upper()
    return bool(av and av in (state.get("av_numbers") or {}))


def state_has_uri(state: dict[str, Any], uri: str) -> bool:
    key = item_download_key({"uri": uri, "url": uri, "magnet": uri})
    uris = state.get("uris") or {}
    if key and key in uris:
        return True
    btih = extract_btih(uri)
    if btih and f"btih:{btih}" in uris:
        return True
    return False


def state_has_row(state: dict[str, Any], row: dict[str, Any]) -> bool:
    av = (row.get("av_number") or "").strip().upper()
    if state_has_av(state, av):
        return True
    uri = row.get("uri") or row.get("url") or ""
    return state_has_uri(state, uri)


def mark_row_submitted(
    state: dict[str, Any],
    row: dict[str, Any],
    *,
    task_id: str | None = None,
) -> None:
    uri = str(row.get("uri") or row.get("url") or "").strip()
    av = (row.get("av_number") or "").strip().upper()
    key = item_download_key({"uri": uri, "url": uri, "magnet": uri}) or f"uri:{uri}"
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rec: dict[str, Any] = {"uri": uri, "av_number": av, "at": stamp}
    if task_id:
        rec["task_id"] = task_id
    rec["source_nfo_id"] = row.get("source_nfo_id")
    rec["source_nfo_name"] = row.get("source_nfo_name")
    rec["name"] = row.get("name")
    state.setdefault("uris", {})[key] = rec
    if av:
        state.setdefault("av_numbers", {})[av] = {
            "uri": uri,
            "at": stamp,
            "task_id": task_id,
        }
    state["last_run_utc"] = stamp


def load_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"report not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid report JSON: {path}")
    return data


def iter_report_entries(report: dict[str, Any]) -> list[dict[str, Any]]:
    entries = report.get("entries")
    if isinstance(entries, list) and entries:
        return [e for e in entries if isinstance(e, dict)]
    out: list[dict[str, Any]] = []
    for rec in report.get("records") or []:
        if not isinstance(rec, dict):
            continue
        for url in rec.get("links") or []:
            url = str(url or "").strip()
            if not url:
                continue
            out.append({
                "name": rec.get("name"),
                "av_number": rec.get("av_number"),
                "url": url,
                "link_source": rec.get("link_source"),
                "source_nfo_name": rec.get("source_nfo_name"),
                "source_nfo_id": rec.get("source_nfo_id"),
            })
    return out


def build_av_magnet_queue(report: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per 番号; prefers ``selected_magnet`` on each record."""
    queue: list[dict[str, Any]] = []
    seen_av: set[str] = set()
    for rec in report.get("records") or []:
        if not isinstance(rec, dict):
            continue
        av = canonical_av_number(str(rec.get("av_number") or ""))
        if not av or av in seen_av:
            continue
        links = [str(u).strip() for u in (rec.get("links") or []) if str(u).strip()]
        uri = str(rec.get("selected_magnet") or "").strip()
        if not uri and links:
            hint = str(rec.get("name") or rec.get("source_nfo_name") or av)
            uri, _meta = pick_best_magnet_uri(links, name_hint=hint)
        if not uri or not uri_supported_by_guangya(uri):
            continue
        seen_av.add(av)
        queue.append({
            "name": rec.get("name") or av,
            "av_number": av,
            "uri": uri,
            "url": uri,
            "link_source": rec.get("link_source"),
            "source_nfo_name": rec.get("source_nfo_name"),
            "source_nfo_id": rec.get("source_nfo_id"),
        })
    if queue:
        return queue
    seen_av.clear()
    for raw in iter_report_entries(report):
        av = canonical_av_number(str(raw.get("av_number") or ""))
        if not av or av in seen_av:
            continue
        uri = str(raw.get("url") or raw.get("uri") or "").strip()
        if not uri or not uri_supported_by_guangya(uri):
            continue
        seen_av.add(av)
        queue.append({
            "name": raw.get("name") or av or "save-link",
            "av_number": av,
            "uri": uri,
            "url": uri,
            "link_source": raw.get("link_source"),
            "source_nfo_name": raw.get("source_nfo_name"),
            "source_nfo_id": raw.get("source_nfo_id"),
        })
    return queue


def build_unique_magnet_queue(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Alias for tests and callers — queue is one row per 番号."""
    return build_av_magnet_queue(report)


def batch_delay_seconds() -> float:
    raw = (os.environ.get("GUANGYA_CLOUD_SUBMIT_BATCH_DELAY") or "").strip()
    if not raw:
        return DEFAULT_BATCH_DELAY_SEC
    try:
        val = float(raw)
    except ValueError:
        return DEFAULT_BATCH_DELAY_SEC
    return max(0.0, val)


def ensure_logged_in(*, sync_auth: bool = True) -> None:
    if sync_auth:
        sync_credentials_from_skill_store()
    code, payload, stderr = login_status()
    logged_in = (payload.get("data") or {}).get("logged_in")
    if code != 0 or logged_in is not True:
        raise RuntimeError(
            "GuangYa not logged in: run guangyapan-drive login on this profile "
            f"(GUANGYAPAN_PROFILE_DIR); login-status={logged_in!r} {stderr or payload}",
        )


def submit_rows_with_batch_delay(
    rows: list[dict[str, Any]],
    *,
    remote_parent_id: str,
    preflight: bool = False,
    batch_size: int | None = None,
) -> dict[str, Any]:
    if not rows:
        return {"submitted": 0, "results": [], "batches": 0, "exit_code": 0}

    size = batch_size if batch_size and batch_size > 0 else _cloud_submit_batch_size()
    delay = batch_delay_seconds()
    all_results: list[dict[str, Any]] = []
    exit_code = 0
    stderr_parts: list[str] = []
    batch_count = 0

    for offset in range(0, len(rows), size):
        chunk = rows[offset : offset + size]
        batch_count += 1
        part = _submit_rows_to_guangya(
            chunk,
            remote_parent_id=remote_parent_id,
            preflight=preflight,
            batch_size=size,
        )
        all_results.extend(part.get("results") or [])
        if part.get("exit_code"):
            exit_code = int(part["exit_code"])
        if part.get("stderr"):
            stderr_parts.append(str(part["stderr"]).strip())
        if delay > 0 and offset + size < len(rows):
            time.sleep(delay)

    return {
        "exit_code": exit_code,
        "stderr": "\n".join(stderr_parts),
        "submitted": len(rows),
        "results": all_results,
        "batches": batch_count,
        "batch_size": size,
        "batch_delay_sec": delay,
    }


def resolve_remote_parent_id(report: dict[str, Any], override: str | None) -> str:
    if override and override.strip():
        return override.strip()
    fid = str(report.get("guangya_folder_id") or "").strip()
    return fid or DEFAULT_SAVE_FOLDER_ID


def select_pending_rows(
    queue: list[dict[str, Any]],
    state: dict[str, Any],
    *,
    start_index: int,
    limit: int,
    already_on_save: set[str] | None = None,
) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
    """Return (rows to submit, next_index after scan, skip counts while scanning)."""
    stats = {
        "skipped_state": 0,
        "skipped_unsupported": 0,
        "skipped_already_on_save": 0,
    }
    on_save = (
        already_on_save
        if already_on_save is not None
        else load_already_on_save_avs(state=state)
    )
    pending: list[dict[str, Any]] = []
    idx = max(0, start_index)
    while idx < len(queue) and (limit <= 0 or len(pending) < limit):
        row = queue[idx]
        idx += 1
        av = canonical_av_number(str(row.get("av_number") or ""))
        if av and av in on_save:
            stats["skipped_already_on_save"] += 1
            continue
        uri = row.get("uri") or ""
        if not uri_supported_by_guangya(uri):
            stats["skipped_unsupported"] += 1
            continue
        if state_has_row(state, row):
            stats["skipped_state"] += 1
            continue
        pending.append(row)
    return pending, idx, stats


def run_batch(
    *,
    apply: bool,
    limit: int,
    day: int | None,
    report_path: Path,
    state_path: Path,
    parent_id_override: str | None,
    preflight: bool,
    sync_auth: bool,
    ignore_state: bool,
    quiet: bool = False,
) -> dict[str, Any]:
    report = load_report(report_path)
    queue = build_av_magnet_queue(report)
    remote_parent_id = resolve_remote_parent_id(report, parent_id_override)

    state = empty_state() if ignore_state else load_state(state_path)
    already_on_save = load_already_on_save_avs(state=None if ignore_state else state)
    if not ignore_state:
        state["schema_version"] = STATE_SCHEMA_VERSION
        state["queue_mode"] = "one_magnet_per_av"
        state["report_path"] = str(report_path)
        state["report_generated_at_utc"] = report.get("generated_at_utc")
        state["remote_parent_id"] = remote_parent_id
        state["queue_av_count"] = len(queue)
        state["already_in_save_av"] = sorted(already_on_save)

    start_index = 0 if ignore_state else int(state.get("next_queue_index") or 0)
    if start_index > len(queue):
        start_index = len(queue)

    pending, next_index, scan_stats = select_pending_rows(
        queue,
        state if not ignore_state else {"uris": {}, "av_numbers": {}},
        start_index=start_index,
        limit=limit if limit > 0 else 0,
        already_on_save=already_on_save,
    )

    stats: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run",
        "day": day,
        "beijing_now": beijing_now_iso(),
        "report_path": str(report_path),
        "remote_parent_id": remote_parent_id,
        "queue_av_total": len(queue),
        "queue_unique_total": len(queue),
        "already_on_save_count": len(already_on_save),
        "queue_start_index": start_index,
        "queue_next_index": next_index,
        "planned": len(pending),
        "skipped_state": scan_stats["skipped_state"],
        "skipped_unsupported": scan_stats["skipped_unsupported"],
        "skipped_already_on_save": scan_stats["skipped_already_on_save"],
        "submitted": 0,
        "failed": 0,
        "sample_planned": pending[0] if pending else None,
    }

    if not quiet:
        for row in pending[:5]:
            uri = row.get("uri") or ""
            av = row.get("av_number") or "?"
            print(
                f"[plan] {av} {uri[:80]}{'…' if len(uri) > 80 else ''}",
            )
        if len(pending) > 5:
            print(f"[plan] … and {len(pending) - 5} more")

    if apply and pending:
        ensure_logged_in(sync_auth=sync_auth)
        submit_result = submit_rows_with_batch_delay(
            pending,
            remote_parent_id=remote_parent_id,
            preflight=preflight,
        )
        stats["guangya"] = submit_result
        stats["submitted"] = submit_result.get("submitted", 0)
        failed = 0
        for res in submit_result.get("results") or []:
            uri = str(res.get("uri") or "")
            av = str(res.get("av_number") or "")
            task_id = str(res.get("task_id") or "")
            if not uri:
                failed += 1
                continue
            print(f"[ok] {av} task={task_id or '?'}")
            if not ignore_state:
                match = next((r for r in pending if r.get("uri") == uri), {"uri": uri, "av_number": av})
                mark_row_submitted(state, match, task_id=task_id or None)
        stats["failed"] = failed
        if not ignore_state:
            state["next_queue_index"] = next_index
            if day is not None:
                day_key = str(day)
                prev = state.setdefault("days", {}).get(day_key) or {}
                state["days"][day_key] = {
                    "at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "at_beijing": beijing_now_iso(),
                    "submitted": int(prev.get("submitted") or 0) + stats["submitted"],
                    "failed": int(prev.get("failed") or 0) + failed,
                    "skipped_state": int(prev.get("skipped_state") or 0)
                    + scan_stats["skipped_state"],
                    "skipped_already_on_save": int(prev.get("skipped_already_on_save") or 0)
                    + scan_stats["skipped_already_on_save"],
                    "planned": len(pending),
                    "queue_next_index": next_index,
                }
            save_state(state_path, state)
    elif not ignore_state and not apply:
        # Dry-run: do not advance cursor (only apply moves the queue).
        state["next_queue_index"] = start_index
        save_state(state_path, state)

    if submit_exit := (stats.get("guangya") or {}).get("exit_code"):
        if submit_exit != 0:
            stats["submit_exit_code"] = submit_exit

    return stats


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    load_env_local()
    parser = argparse.ArgumentParser(
        description="GuangYa Save NFO report magnets → Save folder (500/day batches)",
    )
    parser.add_argument(
        "--report",
        default=str(DEFAULT_REPORT_PATH),
        help="Path to guangya_save_nfo_links_*.json",
    )
    parser.add_argument(
        "--state-file",
        default=str(DEFAULT_STATE_PATH),
        help="Progress / dedupe state JSON",
    )
    parser.add_argument(
        "--parent-id",
        default=os.environ.get("GUANGYA_SAVE_FOLDER_ID", "").strip() or None,
        help=f"Save folder id (default: report or {DEFAULT_SAVE_FOLDER_ID})",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Submit cloud_collection_add (default: dry-run plan only)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Max 番号 (one magnet each) to submit this run (default: 500)",
    )
    parser.add_argument(
        "--day",
        type=int,
        default=None,
        choices=(1, 2, 3),
        help="Label this run as day 1/2/3 in state (optional)",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="resolve_cloud_collection before each add",
    )
    parser.add_argument(
        "--no-auth-sync",
        action="store_true",
        help="Skip sync_credentials_from_skill_store before login-status",
    )
    parser.add_argument(
        "--ignore-state",
        action="store_true",
        help="Do not read/write state file",
    )
    parser.add_argument("--json", action="store_true", help="Print stats JSON on stdout")
    args = parser.parse_args()

    try:
        stats = run_batch(
            apply=args.apply,
            limit=args.limit,
            day=args.day,
            report_path=Path(args.report),
            state_path=Path(args.state_file),
            parent_id_override=args.parent_id,
            preflight=args.preflight,
            sync_auth=not args.no_auth_sync,
            ignore_state=args.ignore_state,
            quiet=args.json,
        )
    except Exception as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        print(
            f"[info] mode={stats['mode']} day={stats.get('day')} "
            f"queue_av={stats['queue_av_total']} on_save={stats.get('already_on_save_count', 0)} "
            f"idx={stats['queue_start_index']}→{stats['queue_next_index']} "
            f"planned={stats['planned']} skipped_on_save={stats.get('skipped_already_on_save', 0)} "
            f"skipped_state={stats['skipped_state']} submitted={stats['submitted']} "
            f"failed={stats.get('failed', 0)} parent={stats['remote_parent_id']}",
        )
    exit_code = int(stats.get("submit_exit_code") or 0)
    return exit_code if exit_code else 0


if __name__ == "__main__":
    raise SystemExit(main())
