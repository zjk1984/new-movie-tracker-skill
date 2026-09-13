# -*- coding: utf-8 -*-
"""Unified region + JavDB score gating for download rows (forum + BT refetch)."""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import unquote

from javdb_client import (
    JAVDB_MIN_DOWNLOAD_SCORE,
    JavDBClient,
    ensure_javdb_score_gate,
    extract_av_number,
    is_submit_eligible,
)
from content_filter import apply_region_filter, is_downloadable


def build_submit_probe(
    item: dict[str, Any],
    matched_by_href: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Merge scan thread context with per-link name/uri for gate checks."""
    href = (item.get("href") or "").strip()
    base = dict((matched_by_href or {}).get(href) or {})

    probe: dict[str, Any] = dict(base)
    for key in ("href", "title", "name", "uri", "url", "magnet", "source", "link_type"):
        val = item.get(key)
        if val:
            probe[key] = val

    uri_text = unquote(item.get("uri") or item.get("url") or item.get("magnet") or "")
    number = (
        extract_av_number(item.get("name") or "")
        or extract_av_number(item.get("title") or "")
        or extract_av_number(uri_text)
        or probe.get("av_number")
    )
    if number:
        probe["av_number"] = str(number).upper()
        if not probe.get("name") or probe.get("name") in {"?", "：", ":"}:
            probe["name"] = probe["av_number"]

    # Re-classify compilation/BT rows using per-magnet identity.
    apply_region_filter(probe, region_filter=True)
    return probe


def is_download_row_eligible(
    item: dict[str, Any],
    matched_by_href: dict[str, dict[str, Any]] | None = None,
    client: JavDBClient | None = None,
    *,
    min_score: float = JAVDB_MIN_DOWNLOAD_SCORE,
    query_if_missing: bool = True,
) -> bool:
    probe = build_submit_probe(item, matched_by_href)
    if not is_downloadable(probe):
        return False
    return ensure_javdb_score_gate(
        probe,
        client,
        min_score=min_score,
        query_if_missing=query_if_missing,
    )


def iter_magnets_from_thread(thread: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand a refetched thread into per-magnet download rows."""
    from pikpak_links import parse_download_link

    href = thread.get("href") or ""
    title = thread.get("title") or ""
    magnets: list[str] = list(thread.get("magnets") or [])
    selected = thread.get("selected_download") or thread.get("selected_magnet") or ""
    if selected and selected not in magnets:
        magnets.insert(0, selected)

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for magnet in magnets:
        if not magnet or magnet in seen:
            continue
        seen.add(magnet)
        parsed = parse_download_link(magnet) or {}
        dn = (parsed.get("name") or "").strip()
        number = extract_av_number(dn) or extract_av_number(unquote(magnet))
        rows.append({
            "name": dn or number or title[:60] or "magnet",
            "title": title,
            "href": href,
            "uri": magnet,
            "url": magnet,
            "magnet": magnet,
            "link_type": "magnet",
            "source": thread.get("download_source") or thread.get("magnet_source") or "bt_refetch",
            "av_number": number,
        })
    return rows


def collect_gated_downloads(
    threads: list[dict[str, Any]],
    matched_by_href: dict[str, dict[str, Any]] | None = None,
    client: JavDBClient | None = None,
    *,
    min_score: float = JAVDB_MIN_DOWNLOAD_SCORE,
    query_if_missing: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (eligible, skipped) download rows from refetched threads."""
    own_client = client is None
    if own_client:
        client = JavDBClient()

    eligible: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for thread in threads:
        for row in iter_magnets_from_thread(thread):
            probe = build_submit_probe(row, matched_by_href)
            if is_download_row_eligible(
                row,
                matched_by_href,
                client,
                min_score=min_score,
                query_if_missing=query_if_missing,
            ):
                out = dict(row)
                if probe.get("content_region"):
                    out["content_region"] = probe["content_region"]
                if probe.get("domestic_subtype"):
                    out["domestic_subtype"] = probe["domestic_subtype"]
                if probe.get("javdb_query"):
                    out["javdb_query"] = probe["javdb_query"]
                eligible.append(out)
            else:
                skip = dict(row)
                skip["skip_reason"] = probe.get("skip_reason") or "not_eligible"
                skipped.append(skip)
    return eligible, skipped


def thread_dedup_enabled() -> bool:
    return os.environ.get("DOWNLOAD_DEDUP_THREADS", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def matched_href_map(matched: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    return {m.get("href"): m for m in (matched or []) if m.get("href")}


def filter_download_report(
    report: dict[str, Any],
    matched: list[dict[str, Any]] | None = None,
    client: JavDBClient | None = None,
    *,
    min_score: float = JAVDB_MIN_DOWNLOAD_SCORE,
) -> dict[str, Any]:
    """Drop succeeded rows failing region or JavDB score gates."""
    if not report:
        return report
    href_map = matched_href_map(matched)
    own_client = client is None
    if own_client:
        client = JavDBClient()

    kept: list[dict[str, Any]] = []
    removed = 0
    for item in report.get("succeeded") or []:
        if is_download_row_eligible(
            item,
            href_map,
            client,
            min_score=min_score,
            query_if_missing=True,
        ):
            kept.append(item)
        else:
            removed += 1

    if removed:
        report = dict(report)
        report["succeeded"] = kept
        report["ok"] = len(kept)
        report["total"] = len(kept) + int(report.get("failed_count") or 0)
        report["javdb_score_filtered"] = removed
    return report
