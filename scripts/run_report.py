#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Write per-run Markdown reports under reports/ and optionally push to GitHub."""
from __future__ import annotations

import html
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pikpak_links import normalize_ed2k_uri

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


def _canonical_uri(uri: str) -> str:
    text = (uri or "").strip()
    if text.lower().startswith("ed2k://"):
        return normalize_ed2k_uri(text) or text
    return text


def _collect_fail_uris(failed: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    uris: list[str] = []
    for item in failed:
        uri = _canonical_uri(item.get("uri") or item.get("url") or "")
        if not uri or uri in seen:
            continue
        seen.add(uri)
        uris.append(uri)
    return uris


JAV_REGIONS = frozenset({"jav_censored", "uncensored", "fc2"})
FORUM_SITE_BASE = "https://www.sehuatang.org/"


def _thread_post_url(item: dict[str, Any]) -> str:
    href = (item.get("href") or "").strip()
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return urljoin(FORUM_SITE_BASE, href.lstrip("/"))


def _md_title_line(title: str, thread_url: str) -> str:
    if thread_url:
        return (
            f"**标题**: <a href=\"{html.escape(thread_url, quote=True)}\">"
            f"{html.escape(title)}</a>\n"
        )
    return f"**标题**: `{title}`\n"


def _skip_reason_label(item: dict[str, Any], *, failed_error: str = "") -> str:
    reason = item.get("skip_reason") or ""
    if reason.startswith("javdb_score_low_"):
        score = reason.replace("javdb_score_low_", "")
        return f"JavDB 评分 {score} < 4"
    labels = {
        "javdb_no_score": "JavDB 无评分",
        "javdb_query_error": "JavDB 查询失败",
        "javdb_no_number": "无番号，未提交",
    }
    if reason in labels:
        return labels[reason]
    if failed_error:
        if "task_url_resolve_error" in failed_error:
            return "PikPak 无法解析链接"
        return _truncate(failed_error, 80)
    if reason:
        return reason
    return "未成功下载"


def _collect_post_uris(item: dict[str, Any]) -> list[tuple[str, str]]:
    from pikpak_links import normalize_ed2k_uri, parse_download_link

    seen: set[str] = set()
    out: list[tuple[str, str]] = []

    def add(uri: str, kind: str) -> None:
        canonical = _canonical_uri(uri)
        if not canonical or canonical in seen:
            return
        seen.add(canonical)
        out.append((kind, canonical))

    try:
        from pikpak_download import iter_item_downloads

        for dl in iter_item_downloads(item):
            uri = dl.get("uri") or dl.get("url") or ""
            kind = dl.get("type") or "url"
            if uri.lower().startswith("ed2k:"):
                kind = "ed2k"
            elif uri.lower().startswith("magnet:"):
                kind = "magnet"
            elif kind == "sha":
                kind = "pikpak_sha"
            add(uri, kind)
    except Exception:
        pass

    if out:
        return out

    for ed2k in item.get("ed2k") or []:
        uri = normalize_ed2k_uri(ed2k) or ed2k
        add(uri, "ed2k")
    for magnet in item.get("magnets") or []:
        add(magnet, "magnet")
    selected = item.get("selected_download") or item.get("selected_magnet") or ""
    if selected:
        kind = "ed2k" if selected.lower().startswith("ed2k:") else "magnet"
        add(selected, kind)
    return out


def _index_failed(failed: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, str]]:
    by_uri: dict[str, str] = {}
    by_href: dict[str, str] = {}
    for row in failed:
        uri = _canonical_uri(row.get("uri") or row.get("url") or "")
        err = row.get("error") or ""
        if uri and uri not in by_uri:
            by_uri[uri] = err
        href = row.get("href") or ""
        if href and href not in by_href:
            by_href[href] = err
    return by_uri, by_href


def _build_undownloaded_entries(
    matched: list[dict[str, Any]],
    download_report: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from content_filter import is_downloadable

    succeeded_uris = {
        _canonical_uri(_item_uri(x))
        for x in (download_report.get("succeeded") or [])
        if _item_uri(x)
    }
    failed_by_uri, failed_by_href = _index_failed(download_report.get("failed") or [])

    jav_entries: list[dict[str, Any]] = []
    domestic_entries: list[dict[str, Any]] = []

    for item in matched:
        region = item.get("content_region") or ""
        if region not in JAV_REGIONS and region != "domestic_leak":
            continue
        if not is_downloadable(item):
            continue

        links = _collect_post_uris(item)
        if not links:
            continue

        pending = [(kind, uri) for kind, uri in links if uri not in succeeded_uris]
        if not pending:
            continue

        href = item.get("href") or ""
        errors = [failed_by_uri.get(uri, "") for _, uri in pending if failed_by_uri.get(uri)]
        failed_error = errors[0] if errors else failed_by_href.get(href, "")
        from title_translate import translate_title_for_item

        entry = {
            "title": (item.get("title") or "").replace("\n", " ").strip(),
            "title_zh": translate_title_for_item(item),
            "label": item.get("av_number") or _truncate(item.get("title", ""), 40),
            "reason": _skip_reason_label(item, failed_error=failed_error),
            "links": pending,
            "href": href,
            "thread_url": _thread_post_url(item),
        }
        if region in JAV_REGIONS:
            jav_entries.append(entry)
        else:
            entry["subtype"] = item.get("domestic_subtype") or "其他"
            domestic_entries.append(entry)

    jav_entries.sort(key=lambda x: x.get("label", ""))
    domestic_entries.sort(key=lambda x: (x.get("subtype", ""), x.get("title", "")))
    return jav_entries, domestic_entries


def _md_copyable_links(links: list[tuple[str, str]]) -> str:
    if not links:
        return "_（无链接）_\n"
    if len(links) == 1:
        kind, uri = links[0]
        return f"<pre><code>{html.escape(uri)}</code></pre>\n"
    lines = ["<pre><code>"]
    for i, (kind, uri) in enumerate(links, 1):
        lines.append(html.escape(f"# {i} [{kind}]"))
        lines.append(html.escape(uri))
        if i < len(links):
            lines.append("")
    lines.append("</code></pre>\n")
    return "\n".join(lines)


def _md_undownloaded_posts(
    matched: list[dict[str, Any]],
    download_report: dict[str, Any],
) -> str:
    jav_entries, domestic_entries = _build_undownloaded_entries(matched, download_report)
    total = len(jav_entries) + len(domestic_entries)
    if total == 0:
        return "## 未下载帖子\n\n_（无）_\n"

    lines = [
        "## 未下载帖子\n",
        "> 每条帖子单独列出；选中下方代码块复制链接（多链接时每行一条，`#` 开头为注释可忽略）。\n",
    ]

    if jav_entries:
        lines.append(f"### 日本片（{len(jav_entries)} 帖）\n")
        for entry in jav_entries:
            lines.append(f"#### {entry['label']} · {entry['reason']}\n")
            lines.append(_md_title_line(entry["title"], entry.get("thread_url", "")))
            if entry.get("title_zh"):
                lines.append(f"**中文**: {entry['title_zh']}\n")
            lines.append(_md_copyable_links(entry["links"]))

    if domestic_entries:
        lines.append(f"### 国产（{len(domestic_entries)} 帖）\n")
        for entry in domestic_entries:
            sub = entry.get("subtype") or "其他"
            lines.append(
                f"#### [{sub}] {_truncate(entry['label'], 36)} · {entry['reason']}\n"
            )
            lines.append(_md_title_line(entry["title"], entry.get("thread_url", "")))
            if entry.get("title_zh"):
                lines.append(f"**中文**: {entry['title_zh']}\n")
            lines.append(_md_copyable_links(entry["links"]))

    return "\n".join(lines)


def _md_fail_links(failed: list[dict[str, Any]]) -> str:
    """Render all failed URIs in one HTML pre block (avoids @ → mailto autolink)."""
    if not failed:
        return "_（无）_\n"

    all_uris = _collect_fail_uris(failed)
    lines = [
        "> 选中下方代码区域复制，或使用 GitHub **Copy**（每行一条，含 `|file|` 标准 ed2k 格式）。\n",
        f"### 全部失败链接（{len(all_uris)} 条）\n",
    ]
    if all_uris:
        lines.append("<pre><code>")
        lines.extend(html.escape(u) for u in all_uris)
        lines.append("</code></pre>\n")
    else:
        lines.append("_（无链接）_\n")
    return "\n".join(lines)


def _item_uri(item: dict[str, Any]) -> str:
    return (item.get("uri") or item.get("url") or "").strip()


def merge_download_reports(*reports: dict[str, Any]) -> dict[str, Any]:
    """Merge multiple PikPak download_report payloads, dedupe by URI."""
    succeeded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    seen_ok: set[str] = set()
    seen_fail: set[str] = set()
    sources: list[str] = []

    for report in reports:
        if not report:
            continue
        src = report.get("source")
        if src:
            sources.append(str(src))
        for item in report.get("succeeded") or []:
            uri = _item_uri(item)
            if not uri or uri in seen_ok:
                continue
            seen_ok.add(uri)
            succeeded.append(item)
        for item in report.get("failed") or []:
            uri = _item_uri(item)
            key = uri or f"{item.get('name')}:{item.get('error')}"
            if key in seen_fail:
                continue
            seen_fail.add(key)
            failed.append(item)

    merged: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ok": len(succeeded),
        "failed_count": len(failed),
        "total": len(succeeded) + len(failed),
        "succeeded": succeeded,
        "failed": failed,
    }
    if sources:
        merged["source"] = "; ".join(sources)
    return merged


def _format_success_type(item: dict[str, Any]) -> str:
    base = _infer_link_type(item)
    src = (item.get("source") or "").lower()
    if src in {"bt_refetch", "forum_bt_feature", "forum_bt_seed_code"} or "bt" in src:
        return f"{base} (BT)"
    title = item.get("title") or ""
    if base == "magnet" and ("BT种子" in title or "【BT" in title or "[BT" in title):
        return f"{base} (BT)"
    return base


def _truncate(text: str, limit: int = 60) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _jav_report_rows(matched: list[dict[str, Any]]) -> list[list[str]]:
    from content_filter import is_downloadable

    rows: list[list[str]] = []
    for item in matched:
        region = item.get("content_region") or ""
        if region not in {"jav_censored", "uncensored", "fc2"}:
            continue
        if not is_downloadable(item):
            continue
        number = item.get("av_number") or item.get("title", "")[:20]
        q = item.get("javdb_query") or {}
        if q.get("query_status") == "error":
            rows.append([
                number,
                q.get("content_type_label") or "-",
                "-",
                "-",
                "-",
                q.get("error") or "查询失败",
            ])
            continue
        if not q:
            rows.append([number, "-", "-", "-", "-", "未查询 JavDB"])
            continue
        score = q.get("score")
        rows.append([
            q.get("number") or number,
            q.get("content_type_label") or "-",
            q.get("cnsub_label") or "-",
            f"{score:.2f}" if score is not None else "-",
            q.get("release_date") or "-",
            _truncate(q.get("title") or item.get("title", "")),
        ])
    rows.sort(key=lambda r: (r[4], r[0]), reverse=True)
    return rows


def _domestic_report_sections(matched: list[dict[str, Any]]) -> str:
    from collections import Counter

    from content_filter import is_downloadable

    items = [
        m for m in matched
        if m.get("content_region") == "domestic_leak" and is_downloadable(m)
    ]
    if not items:
        return "## 国产分类\n\n_（无）_\n"

    subtype_counts = Counter(m.get("domestic_subtype") or "其他" for m in items)
    count_lines = "\n".join(
        f"- {name}: **{count}** 帖"
        for name, count in subtype_counts.most_common()
    )

    sections: list[str] = [
        "## 国产分类\n",
        "### 子类统计\n",
        count_lines + "\n",
    ]
    for subtype, _ in subtype_counts.most_common():
        group = [m for m in items if (m.get("domestic_subtype") or "其他") == subtype]
        rows = [
            [
                _truncate(m.get("title", ""), 70),
                "有" if m.get("magnets") or m.get("ed2k") or m.get("selected_download") else "无",
            ]
            for m in group
        ]
        sections.append(f"### {subtype}（{len(group)} 帖）\n")
        sections.append(_md_table(["标题", "链接"], rows))
    return "\n".join(sections)


def _jav_report_section(matched: list[dict[str, Any]], summary: dict[str, Any] | None) -> str:
    summary = summary or {}
    avg = summary.get("avg_score")
    avg_text = f"{avg:.2f}" if avg is not None else "-"
    lines = [
        "## 日本片 JavDB\n",
        "### 汇总\n",
        f"- 可下载日本片: **{summary.get('total', 0)}** 帖\n",
        f"- 已查 JavDB: **{summary.get('queried', 0)}** 帖"
        f"（成功 {summary.get('ok', 0)} / 失败 {summary.get('errors', 0)}）\n",
        f"- 含中字: **{summary.get('with_cnsub', 0)}** 帖"
        f" | 无中字: **{summary.get('without_cnsub', 0)}** 帖\n",
        f"- 平均评分: **{avg_text}**\n",
    ]
    by_type = summary.get("by_content_type") or {}
    if by_type:
        type_line = " | ".join(f"{k} {v}" for k, v in sorted(by_type.items()))
        lines.append(f"- 类型: {type_line}\n")
    lines.append("\n### 明细\n")
    rows = _jav_report_rows(matched)
    lines.append(_md_table(["番号", "类型", "中字", "评分", "发行", "JavDB 标题"], rows))
    return "\n".join(lines)


def _success_rows(succeeded: list[dict[str, Any]]) -> list[list[str]]:
    rows: list[list[str]] = []
    for item in succeeded:
        rows.append([
            item.get("name") or "?",
            _format_success_type(item),
            _item_uri(item),
            item.get("phase") or item.get("status") or "ok",
        ])
    return rows


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

    ok_rows = _success_rows(list(download_report.get("succeeded") or []))

    dl_posts = scan_stats.get("downloadable", 0)
    with_link = scan_stats.get("with_link", 0)
    without_link = scan_stats.get("without_link", 0)
    skipped_jav_score = scan_stats.get("skipped_jav_score", 0)

    jav_summary = scan_stats.get("javdb_summary") or {}
    jav_section = _jav_report_section(scan_stats.get("matched") or [], jav_summary)
    domestic_section = _domestic_report_sections(scan_stats.get("matched") or [])

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
| JavDB 低分/无分跳过 | {skipped_jav_score} | 日本片评分&lt;4 或无评分不下载 |

> **为何可下载 {dl_posts} ≠ PikPak {total}？** {without_link} 帖无链接未提交；有链接帖中多 ed2k 文件按链接逐条提交。日本片 JavDB 评分&lt;4 或无评分不提交 PikPak。

## 下载失败

{_md_fail_links(failed_items)}

{_md_undownloaded_posts(scan_stats.get("matched") or [], download_report)}

## 下载成功

{_md_table(["名称", "类型", "下载链接", "状态"], ok_rows)}

{jav_section}

{domestic_section}
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
