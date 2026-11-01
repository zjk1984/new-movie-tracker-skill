#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit PikPak ``downloads`` vs GuangYa ``downloads`` — report only, no cloud submit."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from env_utils import load_env_local

load_env_local()

from guangya_cloud_cli import find_directory_id, login_status
from guangya_downloads_jav_scrape_lib import list_guangya_dir_paged, walk_guangya_tree
from guangya_cloud_submit import _resolve_pikpak_session
from guangya_cloud_submit_lib import (
    enumerate_av_entries_from_files,
    fetch_pikpak_file_params_url,
)
from javdb_client import JavDBClient, extract_av_number, magnet_uri, sort_magnets
from pikpak_downloads_dedupe_lib import av_number_for_jav_dedupe, pseudo_as_jav_from_env


def _av_from_name(name: str, *, pseudo: bool | None) -> str:
    av = av_number_for_jav_dedupe(name, pseudo_as_jav=pseudo)
    if not av:
        raw = extract_av_number(name)
        av = raw.upper() if raw else ""
    return av or ""


def walk_guangya_files(root_id: str) -> list[dict[str, Any]]:
    return walk_guangya_tree(root_id)


def pikpak_link_for_file(
    session: Any,
    token: str,
    device_id: str,
    user_id: str,
    file_id: str,
) -> tuple[str, str]:
    """Return (url, link_source_detail)."""
    try:
        url = fetch_pikpak_file_params_url(session, token, device_id, user_id, file_id)
    except Exception as exc:
        return "", f"pikpak_fetch_error:{exc}"
    if url:
        return url, "pikpak_params_or_task"
    return "", "pikpak_no_url"


def build_audit(*, javdb_for_pending: bool = True) -> dict[str, Any]:
    pseudo = pseudo_as_jav_from_env(None)
    _, login_payload, _ = login_status()
    logged_in = (login_payload.get("data") or {}).get("logged_in")

    session, token, device_id, user_id, list_all_children, find_folder_id = _resolve_pikpak_session()
    downloads_parent = find_folder_id(session, token, device_id, user_id, "downloads")
    pikpak_files = list_all_children(
        session,
        token,
        device_id,
        user_id,
        parent_id=downloads_parent,
        complete_files_only=True,
    )

    by_av: dict[str, list[dict[str, Any]]] = defaultdict(list)
    no_av_files: list[dict[str, Any]] = []
    for row in pikpak_files:
        if row.get("kind") != "drive#file":
            continue
        name = str(row.get("name") or "")
        av = _av_from_name(name, pseudo=pseudo)
        entry = {
            "file_id": str(row.get("id") or ""),
            "filename": name,
            "av_number": av,
            "size": row.get("size"),
        }
        if av:
            by_av[av].append(entry)
        else:
            no_av_files.append(entry)

    deduped_titles: list[dict[str, Any]] = []
    for av in sorted(by_av):
        group = by_av[av]
        rep = group[0]
        deduped_titles.append(
            {
                "av_number": av,
                "display_name": rep["filename"],
                "file_count": len(group),
                "representative_file_id": rep["file_id"],
                "all_file_ids": [g["file_id"] for g in group],
            },
        )

    pikpak_file_links: list[dict[str, Any]] = []
    for row in pikpak_files:
        if row.get("kind") != "drive#file":
            continue
        name = str(row.get("name") or "")
        av = _av_from_name(name, pseudo=pseudo)
        fid = str(row.get("id") or "")
        url, detail = pikpak_link_for_file(session, token, device_id, user_id, fid)
        pikpak_file_links.append(
            {
                "file_id": fid,
                "filename": name,
                "av_number": av,
                "url": url,
                "link_source": detail if url else detail,
            },
        )

    gy_downloads_id = find_directory_id("downloads")
    gy_files = walk_guangya_files(gy_downloads_id) if gy_downloads_id else []
    guangya_by_av: dict[str, str] = {}
    for row in gy_files:
        name = str(row.get("name") or "")
        av = _av_from_name(name, pseudo=pseudo)
        if av and av not in guangya_by_av:
            guangya_by_av[av] = name

    pikpak_av_set = set(by_av)
    guangya_av_set = set(guangya_by_av)
    missing_av = sorted(pikpak_av_set - guangya_av_set)

    links_by_av: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for link_row in pikpak_file_links:
        av = link_row.get("av_number") or ""
        if av:
            links_by_av[av].append(link_row)

    client = JavDBClient() if javdb_for_pending else None
    pending: list[dict[str, Any]] = []
    for av in missing_av:
        title = deduped_titles[[t["av_number"] for t in deduped_titles].index(av)]
        display = title["display_name"]
        chosen_uri = ""
        link_source = "none"
        javdb_rank: int | None = None
        pikpak_file_id = title["representative_file_id"]

        for link in links_by_av.get(av, []):
            if link.get("url"):
                chosen_uri = str(link["url"])
                link_source = "pikpak"
                pikpak_file_id = link["file_id"]
                break

        if not chosen_uri and client is not None:
            info = client.lookup(av, fetch_magnets=True, best_only=False)
            magnets = sort_magnets(list(info.get("magnet_rows") or []))
            for idx, mag in enumerate(magnets, start=1):
                uri = magnet_uri(mag)
                if uri:
                    chosen_uri = uri
                    link_source = "javdb"
                    javdb_rank = idx
                    break

        pending.append(
            {
                "av_number": av,
                "display_name": display,
                "chosen_uri": chosen_uri,
                "link_source": link_source,
                "javdb_rank": javdb_rank,
                "pikpak_file_id": pikpak_file_id,
                "reason_missing_on_guangya": "not_in_guangya_downloads_tree",
                "pikpak_file_count": title["file_count"],
            },
        )

    pikpak_with_link = sum(1 for r in pikpak_file_links if r.get("url"))
    pending_with_link = sum(1 for r in pending if r.get("chosen_uri"))

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "guangya_logged_in": logged_in,
        "pikpak_downloads_parent_id": downloads_parent,
        "guangya_downloads_folder_id": gy_downloads_id,
        "counts": {
            "pikpak_complete_files": len(pikpak_files),
            "pikpak_deduped_av": len(by_av),
            "pikpak_files_without_av": len(no_av_files),
            "pikpak_file_links_collected": len(pikpak_file_links),
            "pikpak_file_links_with_url": pikpak_with_link,
            "guangya_files": len(gy_files),
            "guangya_deduped_av": len(guangya_by_av),
            "pending_submit_count": len(pending),
            "pending_with_resolved_link": pending_with_link,
            "pending_no_link": len(pending) - pending_with_link,
            "on_guangya_not_pikpak_av": len(guangya_av_set - pikpak_av_set),
        },
        "pikpak_deduped_titles": deduped_titles,
        "pikpak_file_links": pikpak_file_links,
        "guangya_titles_by_av": guangya_by_av,
        "pending_submit": pending,
    }


def write_markdown(audit: dict[str, Any], path: Path) -> None:
    c = audit["counts"]
    lines = [
        "# PikPak vs GuangYa downloads audit (pending submit)",
        "",
        f"- **Generated (UTC)**: {audit['generated_at_utc']}",
        f"- **GuangYa login**: {audit.get('guangya_logged_in')}",
        "- **Action**: report only — no cloud submit until user approves in chat",
        "",
        "## Counts",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| PikPak complete files | {c['pikpak_complete_files']} |",
        f"| PikPak deduped 番号 | {c['pikpak_deduped_av']} |",
        f"| PikPak file link rows | {c['pikpak_file_links_collected']} |",
        f"| PikPak links with URL | {c['pikpak_file_links_with_url']} |",
        f"| GuangYa files (recursive) | {c['guangya_files']} |",
        f"| GuangYa deduped 番号 | {c['guangya_deduped_av']} |",
        f"| **Pending submit** | **{c['pending_submit_count']}** |",
        f"| Pending with resolved link | {c['pending_with_resolved_link']} |",
        f"| Pending no link | {c['pending_no_link']} |",
        "",
        "## Link resolution policy",
        "",
        "1. Prefer PikPak `GET /drive/v1/files/{id}` → `params.url` (task URL fallback).",
        "2. Else JavDB magnets sorted by `javdb_client.sort_magnets` (rank 1 = best).",
        "",
        "## Pending submit (sample first 30)",
        "",
        "| 番号 | display name | link source | JavDB rank | has URI |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for row in audit["pending_submit"][:30]:
        has_uri = "yes" if row.get("chosen_uri") else "no"
        rank = row.get("javdb_rank") if row.get("javdb_rank") is not None else "—"
        lines.append(
            f"| {row['av_number']} | {row['display_name'][:48]} | {row['link_source']} | {rank} | {has_uri} |",
        )
    if len(audit["pending_submit"]) > 30:
        lines.append("")
        lines.append(f"*(+ {len(audit['pending_submit']) - 30} more rows in JSON)*")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="PikPak vs GuangYa downloads audit (no submit)")
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path("reports/pikpak_guangya_audit_2026-11-01.json"),
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        default=Path("reports/pikpak_guangya_audit_2026-11-01.md"),
    )
    parser.add_argument("--no-javdb", action="store_true", help="Skip JavDB fallback for pending")
    parser.add_argument("--json-stdout", action="store_true", help="Print counts JSON to stdout")
    args = parser.parse_args()

    audit = build_audit(javdb_for_pending=not args.no_javdb)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(audit, args.out_md)

    if args.json_stdout:
        print(json.dumps({"counts": audit["counts"], "paths": [str(args.out_json), str(args.out_md)]}, indent=2))
    else:
        print(f"[ok] wrote {args.out_json} and {args.out_md}")
        print(f"[counts] {json.dumps(audit['counts'], ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
