# -*- coding: utf-8 -*-
"""Markdown for PikPak JAV folder JavDB low-score report."""
from __future__ import annotations

from typing import Any

from pikpak_dedupe_report import _md_table


def _format_score(score: float | None) -> str:
    if score is None:
        return "—"
    return f"{float(score):.2f}"


def format_jav_low_score_table_rows(rows: list[dict[str, Any]]) -> list[list[str]]:
    table: list[list[str]] = []
    for row in rows:
        table.append([
            str(row.get("av_number") or ""),
            _format_score(row.get("score")),
            str(row.get("title") or ""),
            str(row.get("tag_labels") or ""),
            str(row.get("release_date") or ""),
            str(row.get("sample_filename") or ""),
        ])
    return table


def build_jav_low_score_section(
    *,
    stats: dict[str, Any],
    rows: list[dict[str, Any]],
    max_score_exclusive: float,
) -> str:
    """Section embedded in PikPak dedupe report."""
    count = len(rows)
    headers = ["番号", "评分", "中文名", "JavDB tags", "发布时间", "JAV 示例文件"]
    table_rows = format_jav_low_score_table_rows(rows)
    av_count = int(stats.get("jav_folder_av_count") or 0)
    queried = int(stats.get("javdb_queried") or 0)
    low = int(stats.get("low_score_count") or count)
    return (
        f"## JAV 低分番号（JavDB 评分 < {max_score_exclusive:g}）\n\n"
        f"- JAV 目录 distinct 番号: **{av_count}** · 已查 JavDB: **{queried}** · "
        f"低分条目: **{low}**（按评分从高到低）\n\n"
        f"{_md_table(headers, table_rows)}"
    )


def build_pikpak_jav_low_score_report_body(
    *,
    generated_at: str,
    folder: str,
    parent_id: str | None,
    stats: dict[str, Any],
    rows: list[dict[str, Any]],
    max_score_exclusive: float,
    previous_line: str = "",
) -> str:
    max_exclusive = float(stats.get("max_score_exclusive") or max_score_exclusive)
    section = build_jav_low_score_section(
        stats=stats,
        rows=rows,
        max_score_exclusive=max_exclusive,
    )
    folder_desc = folder
    if parent_id:
        folder_desc = f"{folder} (parent_id={parent_id})"

    summary_rows = [
        ["PikPak 目录", folder_desc, "仅 completed 文件解析番号"],
        ["distinct 番号", str(stats.get("jav_folder_av_count") or 0), "与 JAV 去重相同 listing"],
        ["JavDB 查询", str(stats.get("javdb_queried") or 0), "fetch_magnets=false，复用 cache"],
        ["查询成功", str(stats.get("javdb_ok") or 0), "query_status=ok"],
        ["有评分", str(stats.get("javdb_with_score") or 0), "score 字段非空"],
        [
            f"评分 < {max_exclusive:g}",
            str(stats.get("low_score_count") or len(rows)),
            "与 Feishu / javdb_client 同一 score 字段",
        ],
    ]

    return f"""# PikPak JAV 低分报告

- **生成时间**: {generated_at}
- **阈值**: JavDB 评分严格小于 {max_exclusive:g}（下载门槛默认 ≥ {max_exclusive:g}）

## 汇总

{previous_line}
{_md_table(["项目", "数值", "说明"], summary_rows)}

{section}
"""
