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


def build_pikpak_dedupe_report_body(
    *,
    generated_at: str,
    folder: str,
    parent_id: str | None,
    apply: bool,
    stats: dict[str, Any],
    groups: list[dict[str, Any]],
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
    trashed_ok = int(stats.get("trashed_ok") or 0)

    summary_rows = [
        ["文件夹", folder_desc, "PikPak 去重目标目录"],
        ["运行模式", mode, "apply 会调用 trash API"],
        ["文件总数", str(total_files), "目录内 drive#file 且已完成"],
        ["番号分组", str(av_groups), "可解析番号的文件组"],
        ["重复番号组", str(duplicate_groups), "同番号 ≥2 个文件"],
        ["无番号跳过", str(skipped_no_av), "文件名未解析出番号"],
        [
            "待删/已删",
            f"{trash_candidates} / {trashed_ok}" if apply else str(trash_candidates),
            "重复组内保留 1 个（UC > C > 体积）",
        ],
    ]

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

    return f"""# PikPak downloads 去重报告

- **生成时间**: {generated_at}
- **运行模式**: {mode}

## 汇总

{previous_line}
{_md_table(["项目", "数值", "说明"], summary_rows)}

{"".join(group_sections)}
"""
