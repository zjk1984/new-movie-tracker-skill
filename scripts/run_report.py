#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Write per-run Markdown reports under reports/ and optionally push to GitHub."""
from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SKILL_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = SKILL_DIR / "reports"


def _github_repo_slug() -> str | None:
    try:
        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=str(SKILL_DIR),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    if remote.startswith("git@"):
        # git@github.com:owner/repo.git
        match = re.search(r"[:/]([^/]+/[^/.]+?)(?:\.git)?$", remote)
        return match.group(1) if match else None
    path = urlparse(remote).path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = path.split("/")
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return None


def current_git_branch() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(SKILL_DIR),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def github_blob_url(rel_path: str, *, branch: str | None = None) -> str | None:
    slug = _github_repo_slug()
    if not slug:
        return None
    branch = branch or current_git_branch() or "main"
    posix = rel_path.replace("\\", "/")
    return f"https://github.com/{slug}/blob/{branch}/{posix}"


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


def write_run_report(
    scan_stats: dict[str, Any],
    download_report: dict[str, Any],
    *,
    reports_dir: Path | None = None,
    run_label: str = "run",
) -> Path:
    out_dir = reports_dir or REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = out_dir / f"{run_label}_{ts}.md"

    forums = scan_stats.get("forums") or {}
    lt = scan_stats.get("link_totals") or {}
    pw = scan_stats.get("posts_with") or {}
    ok = download_report.get("ok", 0)
    fail = download_report.get("failed_count", 0)
    total = download_report.get("total") or (ok + fail)

    forum_lines = "\n".join(f"- {name}: {count} 帖" for name, count in sorted(forums.items()))

    fail_rows = []
    for item in download_report.get("failed") or []:
        err = item.get("error") or ""
        if "task_url_resolve_error" in err:
            err = "URL解析失败"
        fail_rows.append([
            item.get("name") or "?",
            item.get("link_type") or "?",
            item.get("uri") or item.get("url") or "",
            err[:120],
        ])

    ok_rows = []
    for item in download_report.get("succeeded") or []:
        ok_rows.append([
            item.get("name") or "?",
            item.get("link_type") or "?",
            item.get("uri") or item.get("url") or "",
            item.get("phase") or "ok",
        ])

    body = f"""# 论坛扫描报告

- **生成时间**: {datetime.now().isoformat(timespec="seconds")}
- **扫描时间**: {str(scan_stats.get("scan_time", ""))[:19]}

## 扫描总结

### 扫描板块

{forum_lines or "（无）"}

### 统计

| 项目 | 数量 |
| --- | --- |
| 匹配帖 | {scan_stats.get("matched_total", 0)} |
| 可下载 | {scan_stats.get("downloadable", 0)} |
| 磁力链接 | {lt.get("magnet", 0)} ({pw.get("magnet", 0)} 帖) |
| ed2k 链接 | {lt.get("ed2k", 0)} ({pw.get("ed2k", 0)} 帖) |
| BT 种子 | {lt.get("bt", 0)} ({pw.get("bt", 0)} 帖) |
| PikPak 成功 | {ok} |
| PikPak 失败 | {fail} |
| PikPak 合计 | {total} |

## 下载失败

{_md_table(["名称", "类型", "下载链接", "失败原因"], fail_rows)}

## 下载成功

{_md_table(["名称", "类型", "下载链接", "状态"], ok_rows)}
"""
    path.write_text(body, encoding="utf-8")
    return path


def commit_and_push_report(report_path: Path, *, message: str | None = None) -> bool:
    rel = report_path.relative_to(SKILL_DIR)
    branch = current_git_branch()
    if not branch:
        return False
    msg = message or f"docs: add run report {rel.name}"
    try:
        subprocess.run(["git", "add", str(rel)], cwd=str(SKILL_DIR), check=True)
        status = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=str(SKILL_DIR),
        )
        if status.returncode == 0:
            return True
        subprocess.run(["git", "commit", "-m", msg], cwd=str(SKILL_DIR), check=True)
        subprocess.run(["git", "push", "-u", "origin", branch], cwd=str(SKILL_DIR), check=True)
        return True
    except subprocess.CalledProcessError:
        return False
