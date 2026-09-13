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


def _infer_link_type(item: dict[str, Any]) -> str:
    link_type = (item.get("link_type") or item.get("type") or "").strip()
    if link_type and link_type != "url":
        return link_type
    uri = (item.get("uri") or item.get("url") or "").lower()
    if uri.startswith("ed2k:"):
        return "ed2k"
    if uri.startswith("magnet:"):
        return "magnet"
    if uri.startswith("pikpak:"):
        return "pikpak_sha"
    return link_type or "url"


def _format_fail_reason(err: str) -> str:
    text = (err or "").strip()
    if "task_url_resolve_error" in text:
        return "URL解析失败"
    if "not cached" in text.lower() or "no cache" in text.lower():
        return "特征码秒传失败 (PikPak 无缓存)"
    return text[:120] if text else "未知错误"


def _md_fail_links(failed: list[dict[str, Any]]) -> str:
    """Render failed downloads with fenced code blocks for one-click copy."""
    if not failed:
        return "_（无）_\n"

    lines = [
        "> 每条失败链接单独放在代码块中，点击代码块右上角 **Copy** 即可复制完整 URI。\n",
    ]
    for idx, item in enumerate(failed, 1):
        name = (item.get("name") or "?").replace("\n", " ").strip()
        link_type = _infer_link_type(item)
        reason = _format_fail_reason(item.get("error") or "")
        uri = (item.get("uri") or item.get("url") or "").strip()
        lines.append(f"### {idx}. {name} · {link_type} · {reason}\n")
        if uri:
            lines.append("```text")
            lines.append(uri)
            lines.append("```\n")
        else:
            lines.append("_（无链接）_\n")
    return "\n".join(lines)


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

    failed_items = list(download_report.get("failed") or [])

    ok_rows = []
    for item in download_report.get("succeeded") or []:
        ok_rows.append([
            item.get("name") or "?",
            item.get("link_type") or "?",
            item.get("uri") or item.get("url") or "",
            item.get("phase") or "ok",
        ])

    dl_posts = scan_stats.get("downloadable", 0)
    with_link = scan_stats.get("with_link", 0)
    without_link = scan_stats.get("without_link", 0)

    body = f"""# 论坛扫描报告

- **生成时间**: {datetime.now().isoformat(timespec="seconds")}
- **扫描时间**: {str(scan_stats.get("scan_time", ""))[:19]}

## 扫描总结

### 扫描板块

{forum_lines or "（无）"}

### 统计

| 项目 | 数量 | 说明 |
| --- | --- | --- |
| 匹配帖 | {scan_stats.get("matched_total", 0)} | 扫描命中的全部帖子 |
| 可下载(过滤保留) | {dl_posts} | 通过 content_filter 保留的帖 |
| 有链接 | {with_link} | 帖内提取到 magnet/ed2k 等 |
| 无链接 | {without_link} | 标题保留但未抓到链接(需进帖/Cloudflare) |
| 磁力链接 | {lt.get("magnet", 0)} ({pw.get("magnet", 0)} 帖) | 采集到的磁力 URI 数 |
| ed2k 链接 | {lt.get("ed2k", 0)} ({pw.get("ed2k", 0)} 帖) | 含 refetch 进帖结果 |
| BT 种子 | {lt.get("bt", 0)} ({pw.get("bt", 0)} 帖) | BT种子帖/特征码 |
| PikPak 成功 | {ok} | 按**链接**提交成功 |
| PikPak 失败 | {fail} | 按**链接**提交失败 |
| PikPak 合计 | {total} | 成功+失败链接数，非帖数 |

> **为何可下载 {dl_posts} ≠ PikPak {total}？** {without_link} 帖无链接未提交；有链接帖中多 ed2k 文件按链接逐条提交。

## 下载失败

{_md_fail_links(failed_items)}

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
