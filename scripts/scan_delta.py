# -*- coding: utf-8 -*-
"""Filter scan/report items that already appeared in the previous scan."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from download_state import extract_btih


def previous_result_path(output_dir: Path | str) -> Path:
    return Path(output_dir) / "previous_result.json"


def last_result_path(output_dir: Path | str) -> Path:
    return Path(output_dir) / "last_result.json"


def rotate_scan_snapshot(output_dir: Path | str) -> bool:
    """Copy last_result.json -> previous_result.json before a new scan."""
    out = Path(output_dir)
    last_path = last_result_path(out)
    prev_path = previous_result_path(out)
    if not last_path.exists():
        return False
    prev_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(last_path, prev_path)
    return True


def load_previous_matched(output_dir: Path | str) -> list[dict[str, Any]]:
    path = previous_result_path(output_dir)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    matched = data.get("matched") or []
    return matched if isinstance(matched, list) else []


def item_dedup_keys(item: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    href = (item.get("href") or "").strip()
    if href:
        keys.add(f"href:{href}")

    try:
        from javdb_client import extract_av_number

        for src in (
            item.get("av_number"),
            item.get("name"),
            item.get("title"),
            item.get("uri"),
            item.get("url"),
            item.get("magnet"),
        ):
            number = extract_av_number(str(src or ""))
            if number:
                keys.add(f"av:{number.upper()}")
    except ImportError:
        pass

    btih = extract_btih(item.get("uri") or item.get("url") or item.get("magnet") or "")
    if btih:
        keys.add(f"btih:{btih.upper()}")

    title = (item.get("title") or "").replace("\n", " ").strip()
    if title and not keys:
        keys.add(f"title:{title[:120]}")
    return keys


def build_seen_key_set(items: list[dict[str, Any]]) -> set[str]:
    seen: set[str] = set()
    for item in items:
        seen.update(item_dedup_keys(item))
    return seen


def is_item_new(item: dict[str, Any], seen_keys: set[str]) -> bool:
    keys = item_dedup_keys(item)
    if not keys:
        return True
    return not keys.intersection(seen_keys)


def filter_new_matched(
    matched: list[dict[str, Any]],
    previous_matched: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    if not previous_matched:
        return matched, 0
    seen = build_seen_key_set(previous_matched)
    new_items = [item for item in matched if is_item_new(item, seen)]
    repeat_count = len(matched) - len(new_items)
    return new_items, repeat_count


def filter_download_rows(
    rows: list[dict[str, Any]],
    previous_matched: list[dict[str, Any]],
    matched_by_href: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not previous_matched or not rows:
        return rows
    from submit_gate import build_submit_probe

    seen = build_seen_key_set(previous_matched)
    kept: list[dict[str, Any]] = []
    for row in rows:
        probe = build_submit_probe(row, matched_by_href)
        if is_item_new(probe, seen):
            kept.append(row)
    return kept


def filter_new_download_items(
    items: list[dict[str, Any]],
    output_dir: Path | str,
) -> tuple[list[dict[str, Any]], int]:
    """Drop PikPak download rows already present in the previous scan snapshot."""
    previous = load_previous_matched(output_dir)
    if not previous or not items:
        return items, 0
    seen = build_seen_key_set(previous)
    kept = [item for item in items if is_item_new(item, seen)]
    return kept, len(items) - len(kept)


def filter_download_rows_to_matched(
    rows: list[dict[str, Any]],
    matched_items: list[dict[str, Any]],
    matched_by_href: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Keep download rows that belong to the given matched scan items only."""
    if not matched_items:
        return []
    if not rows:
        return []
    from submit_gate import build_submit_probe

    allowed = build_seen_key_set(matched_items)
    kept: list[dict[str, Any]] = []
    for row in rows:
        probe = build_submit_probe(row, matched_by_href)
        if item_dedup_keys(probe).intersection(allowed):
            kept.append(row)
    return kept


def _forum_label(forum_url: str) -> str:
    from feishu_notify import FORUM_LABELS, _forum_key

    key = _forum_key(forum_url)
    return FORUM_LABELS.get(key, key)


def _count_links(item: dict[str, Any]) -> dict[str, int]:
    mags = list(item.get("magnets") or [])
    if item.get("selected_magnet") and item["selected_magnet"] not in mags:
        mags.append(item["selected_magnet"])
    ed2k = list(item.get("ed2k") or [])
    if item.get("selected_ed2k") and item["selected_ed2k"] not in ed2k:
        ed2k.append(item["selected_ed2k"])
    title = item.get("title") or ""
    bt = 0
    if "BT种子" in title or "【BT" in title or "[BT" in title:
        bt = max(
            len([
                e for e in (item.get("hash_entries") or [])
                if e.get("kind") == "hash_label_btih"
            ]),
            len(mags),
            1,
        )
    return {"magnet": len(mags), "ed2k": len(ed2k), "bt": bt}


def recompute_scan_summary(
    scan_stats: dict[str, Any],
    matched: list[dict[str, Any]],
) -> dict[str, Any]:
    """Rebuild count fields from a filtered matched list."""
    from collections import Counter

    from content_filter import is_downloadable
    from pikpak_download import pick_item_download

    forums: Counter[str] = Counter()
    region_counts: Counter[str] = Counter()
    subtype_counts: Counter[str] = Counter()
    link_totals = {"magnet": 0, "ed2k": 0, "bt": 0}
    posts_with = {"magnet": 0, "ed2k": 0, "bt": 0}
    downloadable = 0
    with_link = 0
    without_link = 0
    skipped_jav_score = 0

    for item in matched:
        forums[_forum_label(item.get("forum", ""))] += 1
        region = item.get("content_region") or "other"
        region_counts[region] += 1
        sub = item.get("domestic_subtype")
        if sub:
            subtype_counts[sub] += 1
        if is_downloadable(item):
            downloadable += 1
            if item.get("skip_reason", "").startswith("javdb_"):
                skipped_jav_score += 1
                without_link += 1
            elif pick_item_download(item):
                with_link += 1
            else:
                without_link += 1
        counts = _count_links(item)
        for key in link_totals:
            link_totals[key] += counts[key]
            if counts[key] > 0:
                posts_with[key] += 1

    out = dict(scan_stats)
    out.update({
        "matched": matched,
        "matched_total": len(matched),
        "forums": dict(forums),
        "downloadable": downloadable,
        "with_link": with_link,
        "without_link": without_link,
        "region_counts": dict(region_counts),
        "subtype_counts": dict(subtype_counts),
        "link_totals": link_totals,
        "posts_with": posts_with,
        "skipped_jav_score": skipped_jav_score,
    })
    try:
        from javdb_client import build_javdb_report_summary

        javdb_summary = build_javdb_report_summary(matched)
        javdb_summary["skipped_low_score"] = skipped_jav_score
        out["javdb_summary"] = javdb_summary
    except ImportError:
        pass
    return out


def apply_scan_dedup(
    scan_stats: dict[str, Any],
    download_report: dict[str, Any],
    *,
    output_dir: Path | str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    previous = load_previous_matched(output_dir)
    if not previous:
        scan_stats = dict(scan_stats)
        scan_stats.setdefault("matched_repeat", 0)
        scan_stats.setdefault("matched_total_all", len(scan_stats.get("matched") or []))
        return scan_stats, download_report

    matched_all = list(scan_stats.get("matched") or [])
    new_matched, repeat_count = filter_new_matched(matched_all, previous)
    scan_stats = recompute_scan_summary(scan_stats, new_matched)
    scan_stats["matched_repeat"] = repeat_count
    scan_stats["matched_total_all"] = len(matched_all)

    matched_by_href = {m.get("href"): m for m in matched_all if m.get("href")}
    report = dict(download_report)
    report["succeeded"] = filter_download_rows_to_matched(
        list(report.get("succeeded") or []),
        new_matched,
        matched_by_href,
    )
    report["failed"] = filter_download_rows_to_matched(
        list(report.get("failed") or []),
        new_matched,
        matched_by_href,
    )
    report["ok"] = len(report["succeeded"])
    report["failed_count"] = len(report["failed"])
    report["total"] = report["ok"] + report["failed_count"]
    return scan_stats, report
