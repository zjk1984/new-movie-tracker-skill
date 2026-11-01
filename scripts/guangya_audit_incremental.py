#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append newly seen GuangYa ``downloads`` files to an existing PikPak/GuangYa audit JSON."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from env_utils import load_env_local

load_env_local()

from guangya_cloud_cli import find_directory_id, login_status
from javdb_client import JavDBClient, magnet_uri, sort_magnets
from pikpak_downloads_jav_scrape_lib import is_jav_video_row, is_video_filename
from pikpak_guangya_audit import (
    _av_from_name,
    pikpak_link_for_file,
    walk_guangya_files,
    write_markdown,
)
from guangya_cloud_submit import _resolve_pikpak_session
from pikpak_downloads_dedupe_lib import pseudo_as_jav_from_env


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _link_index_from_report(report: dict[str, Any]) -> dict[str, str]:
    by_av: dict[str, str] = {}
    for row in report.get("pikpak_file_links") or []:
        av = str(row.get("av_number") or "").upper()
        url = str(row.get("url") or "").strip()
        if av and url and av not in by_av:
            by_av[av] = url
    return by_av


def _resolve_link_for_av(
    av: str,
    *,
    report_links: dict[str, str],
    session: Any,
    token: str,
    device_id: str,
    user_id: str,
    pikpak_file_id: str | None,
    javdb_client: JavDBClient | None,
) -> tuple[str, str]:
    av_u = av.upper()
    if report_links.get(av_u):
        return report_links[av_u], "pikpak_report_cache"
    if pikpak_file_id:
        url, detail = pikpak_link_for_file(session, token, device_id, user_id, pikpak_file_id)
        if url:
            return url, "pikpak"
        if detail:
            pass
    if javdb_client and av_u:
        try:
            info = javdb_client.lookup(av_u, fetch_magnets=True, best_only=False)
        except Exception:
            info = {}
        for mag in sort_magnets(list(info.get("magnet_rows") or [])):
            uri = magnet_uri(mag)
            if uri:
                return uri, "javdb"
    return "", "none"


def _current_downloads_videos(
    folder_id: str,
    *,
    pseudo: bool,
) -> dict[str, dict[str, Any]]:
    """Map guangya file id → row info for video files under ``downloads``."""
    out: dict[str, dict[str, Any]] = {}
    for row in walk_guangya_files(folder_id):
        if row.get("type") != "file":
            continue
        name = str(row.get("name") or "")
        if not is_video_filename(name):
            continue
        ok, _ = is_jav_video_row(name, pseudo_as_jav=pseudo)
        if not ok:
            continue
        fid = str(row.get("id") or "").strip()
        if not fid:
            continue
        av = _av_from_name(name, pseudo=pseudo)
        out[fid] = {
            "guangya_file_id": fid,
            "name": name,
            "av_number": av,
            "size": int(row.get("size") or 0),
        }
    return out


def increment_report(
    report_path: Path,
    *,
    guangya_folder: str = "downloads",
    md_path: Path | None = None,
) -> dict[str, Any]:
    _, login_payload, _ = login_status()
    if not (login_payload.get("data") or {}).get("logged_in"):
        raise RuntimeError("GuangYa not logged in")

    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
    else:
        report = {
            "generated_at_utc": _utc_now(),
            "guangya_logged_in": True,
            "guangya_diff_folder": guangya_folder,
            "counts": {},
            "guangya_titles_by_av": {},
            "guangya_new_entries": [],
            "guangya_downloads_snapshot": {"file_ids": [], "updated_at_utc": None},
        }

    folder_id = report.get("guangya_downloads_folder_id") or find_directory_id(guangya_folder)
    if not folder_id:
        raise RuntimeError(f"GuangYa folder not found: {guangya_folder!r}")
    report["guangya_downloads_folder_id"] = folder_id
    report["guangya_diff_folder"] = guangya_folder

    pseudo = pseudo_as_jav_from_env(None)
    current = _current_downloads_videos(folder_id, pseudo=pseudo)
    snapshot = report.setdefault("guangya_downloads_snapshot", {})
    known: set[str] = set(str(x) for x in (snapshot.get("file_ids") or []))

    report.setdefault("guangya_new_entries", [])
    new_entries: list[dict[str, Any]] = list(report.get("guangya_new_entries") or [])
    report_links = _link_index_from_report(report)

    session = token = device_id = user_id = None
    try:
        session, token, device_id, user_id, _list, _find = _resolve_pikpak_session()
    except Exception:
        pass
    javdb = JavDBClient(use_saved_token=True)

    pikpak_by_av: dict[str, str] = {}
    if session and token:
        from guangya_cloud_submit_lib import enumerate_av_entries_from_files
        from pikpak_download import list_all_children

        try:
            parent = _find(session, token, device_id, user_id, "downloads")
            if parent:
                files = list_all_children(
                    session, token, device_id, user_id, parent_id=parent, complete_files_only=True,
                )
                for av, entry in enumerate_av_entries_from_files(files).items():
                    pikpak_by_av[av.upper()] = str(entry.get("file_id") or "")
        except Exception:
            pass

    added_this_run: list[dict[str, Any]] = []
    if not known:
        snapshot["file_ids"] = sorted(current.keys())
        snapshot["updated_at_utc"] = _utc_now()
        snapshot["initialized_baseline"] = True
    else:
        new_ids = sorted(set(current.keys()) - known)
        stamp = _utc_now()
        titles_by_av = dict(report.get("guangya_titles_by_av") or {})
        for fid in new_ids:
            row = current[fid]
            av = str(row.get("av_number") or "").upper()
            pikpak_fid = pikpak_by_av.get(av) if av else None
            url, link_source = _resolve_link_for_av(
                av,
                report_links=report_links,
                session=session,
                token=token or "",
                device_id=device_id or "",
                user_id=user_id or "",
                pikpak_file_id=pikpak_fid,
                javdb_client=javdb,
            )
            entry = {
                "added_at_utc": stamp,
                "guangya_file_id": fid,
                "name": row["name"],
                "av_number": av,
                "url": url,
                "link_source": link_source,
                "size": row.get("size"),
            }
            new_entries.append(entry)
            added_this_run.append(entry)
            known.add(fid)
            if av and av not in titles_by_av:
                titles_by_av[av] = row["name"]
        report["guangya_titles_by_av"] = titles_by_av
        snapshot["file_ids"] = sorted(known)
        snapshot["updated_at_utc"] = stamp

    report["guangya_new_entries"] = new_entries
    report["last_incremental_at_utc"] = _utc_now()
    report["last_incremental_new_count"] = len(added_this_run)
    report.setdefault("generated_at_utc", report["last_incremental_at_utc"])
    report.setdefault("guangya_logged_in", True)
    report.setdefault("pikpak_folder_resolved", "downloads")
    report.setdefault("pikpak_folder_requested", "downloads")
    report.setdefault("pending_submit", report.get("pending_submit") or [])
    counts = dict(report.get("counts") or {})
    for key in (
        "pending_submit_count",
        "pending_with_resolved_link",
        "pending_no_link",
        "pikpak_complete_files",
        "pikpak_deduped_av",
        "pikpak_file_links_collected",
        "pikpak_file_links_with_url",
    ):
        counts.setdefault(key, counts.get(key, 0))

    counts["guangya_files"] = len(walk_guangya_files(folder_id))
    counts["guangya_deduped_av"] = len(report.get("guangya_titles_by_av") or {})
    counts["guangya_new_entries_total"] = len(new_entries)
    report["counts"] = counts

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md_out = md_path or report_path.with_suffix(".md")
    title = "PikPak vs GuangYa downloads audit (pending submit)"
    write_markdown(report, md_out, title=title)
    _append_incremental_md_section(md_out, report)

    return {
        "report_json": str(report_path),
        "added_this_run": len(added_this_run),
        "new_entries_sample": added_this_run[:3],
        "snapshot_file_count": len(snapshot.get("file_ids") or []),
    }


def _append_incremental_md_section(md_path: Path, report: dict[str, Any]) -> None:
    entries = list(report.get("guangya_new_entries") or [])
    lines = [
        "",
        "## New GuangYa downloads (incremental log)",
        "",
        f"- **Last incremental (UTC)**: {report.get('last_incremental_at_utc', '—')}",
        f"- **New this run**: {report.get('last_incremental_new_count', 0)}",
        f"- **Total logged**: {len(entries)}",
        "",
        "| added (UTC) | 番号 | name | link source | url |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in entries[-50:]:
        url = str(row.get("url") or "")[:72]
        if len(str(row.get("url") or "")) > 72:
            url += "…"
        lines.append(
            f"| {row.get('added_at_utc', '')[:19]} | {row.get('av_number', '')} | "
            f"{str(row.get('name', ''))[:40]} | {row.get('link_source', '')} | `{url}` |",
        )
    if len(entries) > 50:
        lines.append("")
        lines.append(f"*(showing last 50 of {len(entries)} in JSON `guangya_new_entries`)*")

    text = md_path.read_text(encoding="utf-8")
    marker = "## New GuangYa downloads (incremental log)"
    if marker in text:
        text = text.split(marker)[0].rstrip() + "\n"
    md_path.write_text(text + "\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Incremental GuangYa downloads → audit JSON")
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(
            __import__("os").environ.get(
                "GUANGYA_AUDIT_REPORT_JSON",
                "reports/pikpak_guangya_audit_2026-11-01.json",
            ),
        ),
        help="Audit JSON path (append guangya_new_entries)",
    )
    parser.add_argument("--md", type=Path, default=None, help="Markdown path (default: same stem .md)")
    parser.add_argument("--json-stdout", action="store_true")
    args = parser.parse_args()

    try:
        result = increment_report(args.report, md_path=args.md)
    except Exception as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 1
    if args.json_stdout:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"[info] added_this_run={result['added_this_run']} "
            f"snapshot_files={result['snapshot_file_count']}",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
