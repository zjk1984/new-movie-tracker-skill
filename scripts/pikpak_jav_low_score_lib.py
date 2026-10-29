# -*- coding: utf-8 -*-
"""JAV folder low JavDB score report helpers (rating < threshold, sort high→low)."""
from __future__ import annotations

from typing import Any, Callable

DEFAULT_MAX_SCORE_EXCLUSIVE = 4.0


def distinct_av_numbers_from_groups(
    groups: dict[str, list[dict[str, Any]]],
) -> list[str]:
    return sorted(groups.keys())


def sample_filename_for_av(
    groups: dict[str, list[dict[str, Any]]],
    av: str,
) -> str:
    rows = groups.get(av) or []
    if not rows:
        return ""
    ordered = sorted(rows, key=lambda r: str(r.get("name") or ""))
    return str(ordered[0].get("name") or "")


def row_from_javdb_query(
    av: str,
    query: dict[str, Any],
    *,
    sample_filename: str = "",
) -> dict[str, Any]:
    tags = query.get("tags") or []
    tag_labels = query.get("tag_labels")
    if tag_labels is None and tags:
        tag_labels = ", ".join(str(t) for t in tags)
    score = query.get("score")
    return {
        "av_number": av,
        "score": float(score) if score is not None else None,
        "title": str(query.get("title") or ""),
        "tag_labels": str(tag_labels or ""),
        "release_date": str(query.get("release_date") or ""),
        "sample_filename": sample_filename,
        "query_status": query.get("query_status"),
        "query_error": query.get("error"),
    }


def filter_low_score_rows(
    rows: list[dict[str, Any]],
    *,
    max_score_exclusive: float = DEFAULT_MAX_SCORE_EXCLUSIVE,
) -> list[dict[str, Any]]:
    """Keep entries with JavDB score strictly below max_score_exclusive (default 4.0)."""
    out: list[dict[str, Any]] = []
    for row in rows:
        score = row.get("score")
        if score is None:
            continue
        if float(score) < float(max_score_exclusive):
            out.append(row)
    return out


def sort_low_score_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort by score descending, then 番号 ascending."""

    def sort_key(row: dict[str, Any]) -> tuple[float, str]:
        score = row.get("score")
        val = float(score) if score is not None else -1.0
        return (-val, str(row.get("av_number") or ""))

    return sorted(rows, key=sort_key)


def filter_and_sort_low_score_rows(
    rows: list[dict[str, Any]],
    *,
    max_score_exclusive: float = DEFAULT_MAX_SCORE_EXCLUSIVE,
) -> list[dict[str, Any]]:
    return sort_low_score_rows(
        filter_low_score_rows(rows, max_score_exclusive=max_score_exclusive),
    )


def enrich_av_rows_with_javdb(
    av_numbers: list[str],
    groups: dict[str, list[dict[str, Any]]],
    lookup_fn: Callable[[str], dict[str, Any]],
    *,
    sleep_after_lookup: float = 0.0,
) -> list[dict[str, Any]]:
    """Build one metadata row per 番号 using lookup_fn (typically JavDBClient.lookup)."""
    import time

    rows: list[dict[str, Any]] = []
    for av in av_numbers:
        sample = sample_filename_for_av(groups, av)
        query = lookup_fn(av)
        rows.append(row_from_javdb_query(av, query, sample_filename=sample))
        if sleep_after_lookup > 0:
            time.sleep(sleep_after_lookup)
    return rows


def low_score_stats(
    all_rows: list[dict[str, Any]],
    filtered_rows: list[dict[str, Any]],
    *,
    av_count: int,
    max_score_exclusive: float = DEFAULT_MAX_SCORE_EXCLUSIVE,
) -> dict[str, Any]:
    queried_ok = sum(1 for r in all_rows if r.get("query_status") == "ok")
    with_score = sum(1 for r in all_rows if r.get("score") is not None)
    return {
        "jav_folder_av_count": av_count,
        "javdb_queried": len(all_rows),
        "javdb_ok": queried_ok,
        "javdb_with_score": with_score,
        "low_score_count": len(filtered_rows),
        "max_score_exclusive": max_score_exclusive,
    }
