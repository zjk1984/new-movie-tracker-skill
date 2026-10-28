# -*- coding: utf-8 -*-
"""Markdown body builder for PikPak downloads dedupe reports."""
from __future__ import annotations

from typing import Any


def variant_rank_label(rank: int) -> str:
    if rank >= 2:
        return "UC"
    if rank == 1:
        return "C"
    return "普通"


def format_file_size(size: int) -> str:
    n = int(size or 0)
    if n >= 1_073_741_824:
        return f"{n / 1_073_741_824:.2f} GiB ({n:,} B)"
    if n >= 1_048_576:
        return f"{n / 1_048_576:.2f} MiB ({n:,} B)"
    return f"{n:,} B"


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_（无）_\n"
    esc = lambda s: (s or "").replace("|", "\\|").replace("\n", " ")
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(esc(c) for c in row) + " |")
    return "\n".join(lines) + "\n"


def _format_jav_groups(apply: bool, groups: list[dict[str, Any]]) -> str:
    group_sections: list[str] = []
    if groups:
        group_sections.append(f"## 重复番号明细（{len(groups)} 组）\n")
        for entry in groups:
            av = entry.get("av_number") or "?"
            keeper = entry.get("keeper") or {}
            trash_list = list(entry.get("trash") or [])
            k_rank = int(keeper.get("variant_rank") or 0)
            k_name = keeper.get("name") or ""
            k_size = int(keeper.get("size") or 0)
            group_sections.append(
                f"### {av}\n\n"
                f"- **保留**: {variant_rank_label(k_rank)} · "
                f"{format_file_size(k_size)} · `{k_name}`\n",
            )
            if trash_list:
                trash_label = "已移入回收站" if apply else "将删除（预览）"
                rows = []
                for row in trash_list:
                    raw_variant = row.get("variant")
                    if isinstance(raw_variant, str):
                        t_rank_label = raw_variant
                    else:
                        t_rank = int(
                            raw_variant
                            if raw_variant is not None
                            else row.get("variant_rank") or 0
                        )
                        t_rank_label = variant_rank_label(t_rank)
                    status = ""
                    if apply:
                        ok = row.get("trashed_ok")
                        status = "成功" if ok else "失败"
                    rows.append([
                        t_rank_label,
                        format_file_size(int(row.get("size") or 0)),
                        row.get("name") or "",
                        row.get("id") or "",
                        status,
                    ])
                headers = ["版本", "大小", "文件名", "file id", "删除"]
                if not apply:
                    headers = headers[:-1]
                    rows = [r[:-1] for r in rows]
                group_sections.append(f"**{trash_label}**（{len(trash_list)} 个）\n\n")
                group_sections.append(_md_table(headers, rows))
            else:
                group_sections.append("_（无待删文件）_\n")
    else:
        group_sections.append("## 重复番号明细\n\n_（无重复番号组）_\n")
    return "".join(group_sections)


def _format_cross_folder_groups(apply: bool, groups: list[dict[str, Any]]) -> str:
    group_sections: list[str] = []
    if groups:
        group_sections.append(f"## 跨目录重复番号（保留 downloads，{len(groups)} 组）\n")
        for entry in groups:
            av = entry.get("av_number") or "?"
            keeper = entry.get("keeper") or {}
            keeper_folder = entry.get("keeper_folder") or keeper.get("folder") or "downloads"
            trash_list = list(entry.get("trash") or [])
            k_rank = int(keeper.get("variant_rank") or 0)
            k_name = keeper.get("name") or ""
            k_size = int(keeper.get("size") or 0)
            group_sections.append(
                f"### {av}\n\n"
                f"- **保留**（`{keeper_folder}`）: {variant_rank_label(k_rank)} · "
                f"{format_file_size(k_size)} · `{k_name}`\n",
            )
            if trash_list:
                trash_label = "已移入回收站" if apply else "将删除（预览）"
                rows = []
                for row in trash_list:
                    t_rank = int(row.get("variant_rank") or 0)
                    status = ""
                    if apply:
                        ok = row.get("trashed_ok")
                        status = "成功" if ok else "失败"
                    rows.append([
                        row.get("folder") or "?",
                        variant_rank_label(t_rank),
                        format_file_size(int(row.get("size") or 0)),
                        row.get("name") or "",
                        row.get("id") or "",
                        status,
                    ])
                headers = ["来源目录", "版本", "大小", "文件名", "file id", "删除"]
                if not apply:
                    headers = headers[:-1]
                    rows = [r[:-1] for r in rows]
                group_sections.append(f"**{trash_label}**（{len(trash_list)} 个）\n\n")
                group_sections.append(_md_table(headers, rows))
            else:
                group_sections.append("_（无待删文件）_\n")
    else:
        group_sections.append("## 跨目录重复番号\n\n_（无跨目录重复组）_\n")
    return "".join(group_sections)


def _format_domestic_groups(apply: bool, groups: list[dict[str, Any]]) -> str:
    group_sections: list[str] = []
    if groups:
        group_sections.append(f"## 无番号 / 国产去重（{len(groups)} 组）\n")
        for entry in groups:
            group_key = entry.get("group_key") or "?"
            keeper = entry.get("keeper") or {}
            trash_list = list(entry.get("trash") or [])
            k_name = keeper.get("name") or ""
            k_size = int(keeper.get("size") or 0)
            group_sections.append(
                f"### `{group_key}`\n\n"
                f"- **保留**: {format_file_size(k_size)} · `{k_name}`\n",
            )
            if trash_list:
                trash_label = "已移入回收站" if apply else "将删除（预览）"
                rows = []
                for row in trash_list:
                    status = ""
                    if apply:
                        ok = row.get("trashed_ok")
                        status = "成功" if ok else "失败"
                    rows.append([
                        format_file_size(int(row.get("size") or 0)),
                        row.get("name") or "",
                        row.get("id") or "",
                        status,
                    ])
                headers = ["大小", "文件名", "file id", "删除"]
                if not apply:
                    headers = headers[:-1]
                    rows = [r[:-1] for r in rows]
                group_sections.append(f"**{trash_label}**（{len(trash_list)} 个）\n\n")
                group_sections.append(_md_table(headers, rows))
            else:
                group_sections.append("_（无待删文件）_\n")
    else:
        group_sections.append("## 无番号 / 国产去重\n\n_（无国产重复组）_\n")
    return "".join(group_sections)


def _format_domestic_small_trash(apply: bool, rows: list[dict[str, Any]], min_bytes: int) -> str:
    min_mib = min_bytes / (1024 * 1024) if min_bytes else 30
    title = f"## 国产过小文件 (<{min_mib:.0f}MB)\n"
    if not rows:
        return f"{title}\n_（无过小国产文件待删）_\n"
    trash_label = "已移入回收站" if apply else "将删除（预览）"
    table_rows: list[list[str]] = []
    for row in rows:
        status = ""
        if apply:
            ok = row.get("trashed_ok")
            status = "成功" if ok else "失败"
        table_rows.append([
            row.get("folder") or "—",
            format_file_size(int(row.get("size") or 0)),
            row.get("name") or "",
            row.get("id") or "",
            status,
        ])
    headers = ["目录", "大小", "文件名", "file id", "删除"]
    if not apply:
        headers = headers[:-1]
        table_rows = [r[:-1] for r in table_rows]
    return (
        f"{title}\n"
        f"**{trash_label}**（{len(rows)} 个，阈值 {format_file_size(min_bytes)}）\n\n"
        f"{_md_table(headers, table_rows)}"
    )


def build_pikpak_dedupe_report_body(
    *,
    generated_at: str,
    folder: str,
    parent_id: str | None,
    apply: bool,
    stats: dict[str, Any],
    groups: list[dict[str, Any]],
    cross_folder_groups: list[dict[str, Any]] | None = None,
    domestic_groups: list[dict[str, Any]] | None = None,
    domestic_small_trash: list[dict[str, Any]] | None = None,
    previous_line: str = "",
) -> str:
    mode = "执行（已移入回收站）" if apply else "预览（dry-run，未删除）"
    folder_desc = folder
    if parent_id:
        folder_desc = f"{folder} (parent_id={parent_id})"

    total_files = int(stats.get("total_files") or 0)
    av_groups = int(stats.get("av_groups") or 0)
    duplicate_groups = int(stats.get("duplicate_groups") or 0)
    skipped_no_av = int(stats.get("skipped_no_av") or 0)
    trash_candidates = int(stats.get("trash_candidates") or 0)
    domestic_duplicate_groups = int(stats.get("domestic_duplicate_groups") or 0)
    domestic_trash_candidates = int(stats.get("domestic_trash_candidates") or 0)
    domestic_candidates = int(stats.get("domestic_candidates") or 0)
    domestic_small_trash_candidates = int(stats.get("domestic_small_trash_candidates") or 0)
    domestic_small_min_bytes = int(stats.get("domestic_small_min_bytes") or 0)
    trashed_ok = int(stats.get("trashed_ok") or 0)
    cross_folder_duplicate_groups = int(stats.get("cross_folder_duplicate_groups") or 0)
    cross_folder_trash_candidates = int(stats.get("cross_folder_trash_candidates") or 0)
    folders_list = stats.get("folders")
    folders_note = ""
    if isinstance(folders_list, list) and folders_list:
        folders_note = ", ".join(str(f) for f in folders_list)

    summary_rows = [
        ["文件夹", folder_desc, "PikPak 去重目标目录"],
        ["运行模式", mode, "apply 会调用 trash API"],
        ["文件总数", str(total_files), "目录内 drive#file 且已完成"],
        ["番号分组", str(av_groups), "可解析番号的文件组"],
        ["重复番号组", str(duplicate_groups), "同番号 ≥2 个文件"],
        ["无番号跳过", str(skipped_no_av), "文件名未解析出番号（或伪番号走国产）"],
        [
            "目录内 JAV 待删",
            str(trash_candidates),
            "各目录内同番号去重（UC > C > 体积）",
        ],
        [
            "跨目录重复组",
            str(cross_folder_duplicate_groups),
            f"同番号跨目录；保留 downloads"
            + (f"（扫描: {folders_note}）" if folders_note else ""),
        ],
        [
            "跨目录待删",
            str(cross_folder_trash_candidates),
            "downloads 保留 1 个，其它目录同番号全删",
        ],
        [
            "JAV 待删合计",
            str(trash_candidates + cross_folder_trash_candidates),
            "目录内 + 跨目录（去重 file id 后执行）",
        ],
        [
            "已移入回收站",
            str(trashed_ok) if apply else "—",
            "apply 模式下实际 trash 成功数",
        ],
        ["国产候选", str(domestic_candidates), "无番号 / 伪番号（默认）文件数"],
        ["国产重复组", str(domestic_duplicate_groups), "btih / hash / 标题归一化 ≥2"],
        [
            "国产待删/已删",
            str(domestic_trash_candidates),
            "保留体积最大，同名按文件名排序",
        ],
        [
            "国产过小待删",
            str(domestic_small_trash_candidates),
            f"My Pack 等目录内 <{domestic_small_min_bytes / (1024 * 1024):.0f} MiB 国产文件"
            if domestic_small_min_bytes
            else "国产过小文件（未运行或已跳过）",
        ],
    ]

    jav_section = _format_jav_groups(apply, groups)
    cross_section = _format_cross_folder_groups(apply, cross_folder_groups or [])
    domestic_section = _format_domestic_groups(apply, domestic_groups or [])
    domestic_small_section = _format_domestic_small_trash(
        apply,
        domestic_small_trash or [],
        domestic_small_min_bytes or 30 * 1024 * 1024,
    )

    return f"""# PikPak downloads 去重报告

- **生成时间**: {generated_at}
- **运行模式**: {mode}

## 汇总

{previous_line}
{_md_table(["项目", "数值", "说明"], summary_rows)}

{jav_section}
{cross_section}
{domestic_section}
{domestic_small_section}
"""
