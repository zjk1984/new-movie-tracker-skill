#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Write per-run Markdown reports under reports/ and optionally push to GitHub."""
from __future__ import annotations

import html
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import beijing_now, format_beijing_time
from pikpak_links import normalize_ed2k_uri

SKILL_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = SKILL_DIR / "reports"
REPORTS_BACKUP_DIR = REPORTS_DIR / "backup"
REPORT_NAME_RE = re.compile(
    r"^(?:run|scan|daily|custom)_(\d{4}-\d{2}-\d{2}_\d{6})\.md$",
    re.IGNORECASE,
)


class RunReportResult(NamedTuple):
    path: Path
    archived_paths: list[Path]
    previous_report: Path | None


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


def _report_sort_key(path: Path) -> tuple[str, str]:
    match = REPORT_NAME_RE.match(path.name)
    if match:
        return match.group(1), path.name
    return str(path.stat().st_mtime), path.name


def _report_name_prefix(run_label: str) -> str:
    return f"{run_label}_"


def _matches_run_label(path: Path, run_label: str) -> bool:
    return path.name.startswith(_report_name_prefix(run_label))


def _list_report_md_files(directory: Path, *, run_label: str | None = None) -> list[Path]:
    if not directory.is_dir():
        return []
    files = [p for p in directory.glob("*.md") if p.is_file()]
    if run_label:
        files = [p for p in files if _matches_run_label(p, run_label)]
    return sorted(files, key=_report_sort_key, reverse=True)


def _unique_backup_dest(backup_dir: Path, name: str) -> Path:
    dest = backup_dir / name
    if not dest.exists():
        return dest
    stem = Path(name).stem
    suffix = Path(name).suffix
    n = 1
    while dest.exists():
        dest = backup_dir / f"{stem}_{n}{suffix}"
        n += 1
    return dest


def archive_reports_to_backup(
    reports_dir: Path,
    run_label: str,
) -> tuple[Path | None, list[Path]]:
    """Move same-label reports/*.md into reports/backup/; return previous of that label."""
    backup_dir = reports_dir / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    root_reports = _list_report_md_files(reports_dir, run_label=run_label)
    archived: list[Path] = []
    if root_reports:
        for path in root_reports:
            dest = _unique_backup_dest(backup_dir, path.name)
            path.rename(dest)
            archived.append(dest)
        return archived[0], archived
    backup_reports = _list_report_md_files(backup_dir, run_label=run_label)
    return (backup_reports[0] if backup_reports else None), archived


def _previous_report_line(
    previous: Path | None,
    *,
    reports_dir: Path,
) -> str:
    if not previous:
        return ""
    rel_to_reports = previous.relative_to(reports_dir)
    link_path = rel_to_reports.as_posix()
    label = previous.name
    url: str | None = None
    try:
        url = github_blob_url(
            str(previous.relative_to(SKILL_DIR)),
            branch=report_github_branch(),
        )
    except ValueError:
        pass
    if url:
        return f"- **上一份报告**: [{label}]({url})\n"
    return f"- **上一份报告**: [{label}]({link_path})\n"


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


def _matched_note(scan_stats: dict[str, Any]) -> str:
    matched_repeat = scan_stats.get("matched_repeat") or 0
    matched_total_all = scan_stats.get("matched_total_all")
    if matched_total_all is not None and matched_repeat:
        return (
            f"本次新增 **{scan_stats.get('matched_total', 0)}** / "
            f"扫描共 **{matched_total_all}**（重复 **{matched_repeat}** 已隐藏）"
        )
    if matched_repeat:
        return f"本次新增（相对上次扫描已隐藏 **{matched_repeat}** 条重复）"
    return "扫描日期范围内命中的全部帖子（含后续会被过滤的类型）"


def scan_funnel_stats_rows(
    scan_stats: dict[str, Any],
    download_report: dict[str, Any],
) -> list[list[str]]:
    """Statistics table rows ordered by scan → filter → submit funnel."""
    lt = scan_stats.get("link_totals") or {}
    pw = scan_stats.get("posts_with") or {}
    ok = download_report.get("ok", 0)
    fail = download_report.get("failed_count", 0)
    total = download_report.get("total") or (ok + fail)
    dl_posts = scan_stats.get("downloadable", 0)
    with_link = scan_stats.get("with_link", 0)
    without_link = scan_stats.get("without_link", 0)
    skipped_jav_score = scan_stats.get("skipped_jav_score", 0)
    link_sum = lt.get("magnet", 0) + lt.get("ed2k", 0) + lt.get("bt", 0)

    return [
        ["匹配帖", str(scan_stats.get("matched_total", 0)), _matched_note(scan_stats)],
        [
            "采集链接合计",
            str(link_sum),
            "全部匹配帖内抓到的 URI 总数（磁力+ed2k+BT；一帖可含多条；含将被过滤的帖）",
        ],
        [
            "磁力链接",
            f"{lt.get('magnet', 0)} ({pw.get('magnet', 0)} 帖)",
            "magnet URI 条数（括号内为至少含 1 条磁力的帖数）",
        ],
        [
            "ed2k 链接",
            f"{lt.get('ed2k', 0)} ({pw.get('ed2k', 0)} 帖)",
            "ed2k URI 条数（含进帖抓取结果）",
        ],
        [
            "BT 种子/特征码",
            f"{lt.get('bt', 0)} ({pw.get('bt', 0)} 帖)",
            "BT 特征码/hash 转 magnet 的条数",
        ],
        [
            "可下载（过滤保留）",
            str(dl_posts),
            "通过 content_filter 的帖（日本有码/无码 + 国产泄密/流出/ed2k 等）",
        ],
        [
            "有链接",
            str(with_link),
            "可下载帖中已选出 magnet/ed2k/特征码 的帖数",
        ],
        [
            "无链接",
            str(without_link),
            "可下载但未抓到或未选出链接（含 JavDB 低分暂记为无链的帖）",
        ],
        [
            "JavDB 低分/无分",
            str(skipped_jav_score),
            "日本片 JavDB 评分&lt;4 或无评分，不提交 PikPak",
        ],
        [
            "PikPak 成功",
            str(ok),
            "按**链接**提交成功（new_only 去重后）",
        ],
        [
            "PikPak 失败",
            str(fail),
            "按**链接**提交失败",
        ],
        [
            "PikPak 合计",
            str(total),
            "成功+失败链接数，**非帖数**（合集帖/多 ed2k 可能 1 帖对应多条）",
        ],
    ]


def scan_funnel_footnote(
    scan_stats: dict[str, Any],
    download_report: dict[str, Any],
) -> str:
    dl_posts = scan_stats.get("downloadable", 0)
    without_link = scan_stats.get("without_link", 0)
    total = download_report.get("total") or download_report.get("ok", 0)
    lt = scan_stats.get("link_totals") or {}
    link_sum = lt.get("magnet", 0) + lt.get("ed2k", 0) + lt.get("bt", 0)
    return (
        f"**数据漏斗**：匹配帖 → 采集链接({link_sum} 条 URI) → 内容过滤({dl_posts} 帖可下载)"
        f" → 选出链接 → JavDB 门控 → PikPak 提交({total} 条)。"
        f"链接条数≠帖数；{without_link} 帖可下载但无链；日本片低分/无分不提交。"
    )


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
    from forum_browser import canonical_thread_href

    href = canonical_thread_href((item.get("href") or "").strip())
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


def _md_table_cell_link(text: str, url: str) -> str:
    text = (text or "").replace("\n", " ").strip() or "?"
    if url:
        return (
            f'<a href="{html.escape(url, quote=True)}">'
            f"{html.escape(text)}</a>"
        )
    return html.escape(text)


def _success_full_title(
    item: dict[str, Any],
    matched_by_href: dict[str, dict[str, Any]],
) -> str:
    href = item.get("href") or ""
    base = matched_by_href.get(href) or {}
    for source in (base, item):
        title = (source.get("title") or "").replace("\n", " ").strip()
        if title:
            return title
    return (item.get("name") or "?").strip()


def _success_display_title(
    item: dict[str, Any],
    matched_by_href: dict[str, dict[str, Any]],
    *,
    is_jav: bool,
) -> tuple[str, str]:
    from submit_gate import build_submit_probe
    from title_translate import translate_title_for_item

    probe = build_submit_probe(item, matched_by_href)
    full_title = _success_full_title(item, matched_by_href)
    thread_url = _thread_post_url(probe if probe.get("href") else item)
    if is_jav:
        display = translate_title_for_item(probe) or full_title
    else:
        display = full_title
    return display, thread_url


def _success_name_cell(
    item: dict[str, Any],
    matched_by_href: dict[str, dict[str, Any]],
    *,
    is_jav: bool,
) -> str:
    display, thread_url = _success_display_title(item, matched_by_href, is_jav=is_jav)
    return _md_table_cell_link(display, thread_url)


def _success_item_label(
    item: dict[str, Any],
    matched_by_href: dict[str, dict[str, Any]],
) -> str:
    from javdb_client import extract_av_number
    from submit_gate import build_submit_probe

    probe = build_submit_probe(item, matched_by_href)
    for key in (
        probe.get("av_number"),
        item.get("name"),
        extract_av_number(item.get("title") or ""),
    ):
        if key and str(key).strip() not in {"?", "：", ":"}:
            return str(key).strip()
    return _truncate(_success_full_title(item, matched_by_href), 40)


def _format_phase_status(phase: str) -> str:
    labels = {
        "PHASE_TYPE_RUNNING": "下载中",
        "PHASE_TYPE_PENDING": "排队中",
        "PHASE_TYPE_COMPLETE": "已完成",
        "ok": "已提交",
        "submitted": "已提交",
    }
    text = (phase or "ok").strip()
    return labels.get(text, text)


def _md_success_item_block(
    item: dict[str, Any],
    matched_by_href: dict[str, dict[str, Any]],
    *,
    is_jav: bool,
    score_lookup: dict[str, float],
) -> str:
    label = _success_item_label(item, matched_by_href)
    link_type = _format_success_type(item)
    phase = _format_phase_status(item.get("phase") or item.get("status") or "ok")
    title, thread_url = _success_display_title(item, matched_by_href, is_jav=is_jav)

    if is_jav:
        score = _success_item_score(
            item,
            score_lookup=score_lookup,
            matched_by_href=matched_by_href,
        )
        header = f"#### {label} · {link_type} · {score} · {phase}\n"
    else:
        subtype = _success_item_subtype(item, matched_by_href)
        header = f"#### [{subtype}] {label} · {link_type} · {phase}\n"

    lines = [header, _md_title_line(title, thread_url)]
    uri = _item_uri(item)
    if uri:
        lines.append(f"<pre><code>{html.escape(uri)}</code></pre>\n")
    return "".join(lines)


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
    succeeded_hrefs = {
        (x.get("href") or "").strip()
        for x in (download_report.get("succeeded") or [])
        if (x.get("href") or "").strip()
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
        href = (item.get("href") or "").strip()
        if links:
            pending = [(kind, uri) for kind, uri in links if uri not in succeeded_uris]
            if not pending:
                continue
        else:
            if href and href in succeeded_hrefs:
                continue
            pending = []

        errors = [failed_by_uri.get(uri, "") for _, uri in pending if failed_by_uri.get(uri)]
        failed_error = errors[0] if errors else failed_by_href.get(href, "")
        from title_translate import translate_title_for_item

        reason = _skip_reason_label(item, failed_error=failed_error)
        if not links and reason == "未成功下载":
            reason = "链接未抓取"

        entry = {
            "title": (item.get("title") or "").replace("\n", " ").strip(),
            "title_zh": translate_title_for_item(item),
            "label": item.get("av_number") or _truncate(item.get("title", ""), 40),
            "reason": reason,
            "links": pending,
            "href": href,
            "thread_url": _thread_post_url(item),
        }
        if region in JAV_REGIONS:
            jav_entries.append(entry)
        else:
            # 已在「下载失败」中列出的国产 ed2k 不再重复展示
            if pending and all(uri in failed_by_uri for _, uri in pending):
                continue
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
        "> 每条帖子单独列出；标题链至论坛帖；有链接时选中下方代码块复制（多链接时每行一条，`#` 开头为注释可忽略）。\n",
    ]

    if jav_entries:
        lines.append(f"### 日本片（{len(jav_entries)} 帖）\n")
        for entry in jav_entries:
            lines.append(f"#### {entry['label']} · {entry['reason']}\n")
            display_title = entry.get("title_zh") or entry["title"]
            lines.append(_md_title_line(display_title, entry.get("thread_url", "")))
            lines.append(_md_copyable_links(entry["links"]))

    if domestic_entries:
        lines.append(f"### 国产（{len(domestic_entries)} 帖）\n")
        for entry in domestic_entries:
            sub = entry.get("subtype") or "其他"
            lines.append(
                f"#### [{sub}] {_truncate(entry['label'], 36)} · {entry['reason']}\n"
            )
            display_title = entry.get("title_zh") or entry["title"]
            lines.append(_md_title_line(display_title, entry.get("thread_url", "")))
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


def _build_jav_score_lookup(matched: list[dict[str, Any]]) -> dict[str, float]:
    from javdb_client import extract_av_number

    lookup: dict[str, float] = {}
    for item in matched:
        q = item.get("javdb_query") or {}
        score = q.get("score")
        if score is None or q.get("query_status") != "ok":
            continue
        for key in (
            item.get("av_number"),
            q.get("number"),
            extract_av_number(item.get("title", "")),
        ):
            if key:
                lookup[key.upper()] = float(score)
    return lookup


def _is_jav_success_item(
    item: dict[str, Any],
    matched_by_href: dict[str, dict[str, Any]],
) -> bool:
    from javdb_client import item_needs_javdb_score
    from submit_gate import build_submit_probe

    probe = build_submit_probe(item, matched_by_href)
    return item_needs_javdb_score(probe)


def _fill_missing_jav_scores(
    succeeded: list[dict[str, Any]],
    score_lookup: dict[str, float],
    matched_by_href: dict[str, dict[str, Any]],
) -> None:
    from javdb_client import JavDBClient, attach_javdb_query, extract_av_number

    missing: set[str] = set()
    for item in succeeded:
        if not _is_jav_success_item(item, matched_by_href):
            continue
        number = extract_av_number(item.get("name") or "") or extract_av_number(
            item.get("title") or "",
        )
        if number and number.upper() not in score_lookup:
            missing.add(number.upper())
    if not missing:
        return
    client = JavDBClient()
    for key in sorted(missing):
        probe = {"av_number": key, "title": key, "name": key}
        attach_javdb_query(probe, client)
        q = probe.get("javdb_query") or {}
        if q.get("query_status") == "ok" and q.get("score") is not None:
            score_lookup[key] = float(q["score"])


def _success_item_score(
    item: dict[str, Any],
    *,
    score_lookup: dict[str, float],
    matched_by_href: dict[str, dict[str, Any]],
) -> str:
    from javdb_client import extract_av_number

    if not _is_jav_success_item(item, matched_by_href):
        return "-"
    number = extract_av_number(item.get("name") or "") or extract_av_number(
        item.get("title") or "",
    )
    if number:
        score = score_lookup.get(number.upper())
        if score is not None:
            return f"{score:.2f}"
    base = matched_by_href.get(item.get("href") or "")
    if base:
        q = base.get("javdb_query") or {}
        score = q.get("score")
        if score is not None and q.get("query_status") == "ok":
            return f"{float(score):.2f}"
    return "-"


def _success_item_subtype(
    item: dict[str, Any],
    matched_by_href: dict[str, dict[str, Any]],
) -> str:
    from content_filter import resolve_domestic_subtype

    base = matched_by_href.get(item.get("href") or "")
    if base:
        subtype = base.get("domestic_subtype")
        if subtype:
            return subtype
        resolved = resolve_domestic_subtype(base)
        if resolved:
            return resolved
    probe = {
        "title": item.get("title") or item.get("name") or "",
        "name": item.get("name") or "",
        "ed2k": item.get("ed2k"),
    }
    return resolve_domestic_subtype(probe) or "其他"


def _split_success_items(
    succeeded: list[dict[str, Any]],
    matched_by_href: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    jav_items: list[dict[str, Any]] = []
    domestic_items: list[dict[str, Any]] = []
    for item in succeeded:
        if _is_jav_success_item(item, matched_by_href):
            jav_items.append(item)
        else:
            domestic_items.append(item)
    return jav_items, domestic_items


def _md_success_sections(
    succeeded: list[dict[str, Any]],
    matched: list[dict[str, Any]] | None = None,
) -> str:
    matched = matched or []
    matched_by_href = {m.get("href"): m for m in matched if m.get("href")}
    jav_items, domestic_items = _split_success_items(succeeded, matched_by_href)

    score_lookup = _build_jav_score_lookup(matched)
    _fill_missing_jav_scores(jav_items, score_lookup, matched_by_href)

    lines = [
        "> 每条成功下载单独列出；标题可点击跳转原帖，下方代码块可复制磁力/ed2k 链接。\n",
    ]
    if jav_items:
        lines.append(f"### 日本片（{len(jav_items)} 条）\n")
        for item in jav_items:
            lines.append(
                _md_success_item_block(
                    item,
                    matched_by_href,
                    is_jav=True,
                    score_lookup=score_lookup,
                ),
            )
    else:
        lines.append("### 日本片（0 条）\n\n_（无）_\n")

    if domestic_items:
        lines.append(f"### 国产（{len(domestic_items)} 条）\n")
        for item in domestic_items:
            lines.append(
                _md_success_item_block(
                    item,
                    matched_by_href,
                    is_jav=False,
                    score_lookup=score_lookup,
                ),
            )
    else:
        lines.append("### 国产（0 条）\n\n_（无）_\n")

    return "\n".join(lines)


def write_run_report(
    scan_stats: dict[str, Any],
    download_report: dict[str, Any],
    *,
    reports_dir: Path | None = None,
    run_label: str = "run",
) -> RunReportResult:
    out_dir = reports_dir or REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    previous_report, archived_paths = archive_reports_to_backup(out_dir, run_label)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = out_dir / f"{run_label}_{ts}.md"
    previous_line = _previous_report_line(previous_report, reports_dir=out_dir)

    forums = scan_stats.get("forums") or {}
    forum_lines = "\n".join(f"- {name}: {count} 帖" for name, count in sorted(forums.items()))

    failed_items = list(download_report.get("failed") or [])

    success_section = _md_success_sections(
        list(download_report.get("succeeded") or []),
        scan_stats.get("matched") or [],
    )

    matched_repeat = scan_stats.get("matched_repeat") or 0
    stats_table = _md_table(
        ["项目", "数量", "说明"],
        scan_funnel_stats_rows(scan_stats, download_report),
    )
    funnel_note = scan_funnel_footnote(scan_stats, download_report)

    jav_summary = scan_stats.get("javdb_summary") or {}
    jav_section = _jav_report_section(scan_stats.get("matched") or [], jav_summary)
    domestic_section = _domestic_report_sections(scan_stats.get("matched") or [])
    duplicate_line = (
        f"- **重复过滤**: 相对上次扫描隐藏 **{matched_repeat}** 条已出现剧集\n"
        if matched_repeat
        else ""
    )

    body = f"""# 论坛扫描报告

- **生成时间**: {format_beijing_time(beijing_now())}
- **扫描时间**: {format_beijing_time(scan_stats.get("scan_time")) or "（无）"}

## 扫描总结

{previous_line}{duplicate_line}
### 扫描板块

{forum_lines or "（无）"}

### 统计（数据漏斗）

{stats_table}
> {funnel_note}

## 下载失败

{_md_fail_links(failed_items)}

{_md_undownloaded_posts(scan_stats.get("matched") or [], download_report)}

## 下载成功

{success_section}

{jav_section}

{domestic_section}
"""
    path.write_text(body, encoding="utf-8")
    return RunReportResult(path=path, archived_paths=archived_paths, previous_report=previous_report)


def report_github_branch() -> str:
    return (os.environ.get("REPORT_GITHUB_BRANCH") or "main").strip() or "main"


def commit_and_push_report(
    report_path: Path,
    *,
    archived_paths: list[Path] | None = None,
    message: str | None = None,
    push_branch: str | None = None,
) -> bool:
    """Commit report files and push to main (or REPORT_GITHUB_BRANCH).

    Reports always land on the default report branch so Feishu summary links
    stay valid even when the agent runs on a feature branch.
    """
    rel = report_path.relative_to(SKILL_DIR)
    current = current_git_branch()
    target = push_branch or report_github_branch()
    if not current:
        return False
    msg = message or f"docs: add run report {rel.name}"
    paths_to_add = [rel] + [
        archived.relative_to(SKILL_DIR) for archived in (archived_paths or [])
    ]
    try:
        subprocess.run(
            ["git", "fetch", "origin", target],
            cwd=str(SKILL_DIR),
            check=True,
        )
        subprocess.run(["git", "checkout", target], cwd=str(SKILL_DIR), check=True)
        subprocess.run(["git", "pull", "origin", target], cwd=str(SKILL_DIR), check=True)
        for path_rel in paths_to_add:
            subprocess.run(["git", "add", "-f", str(path_rel)], cwd=str(SKILL_DIR), check=True)
        subprocess.run(["git", "add", "-u", "reports"], cwd=str(SKILL_DIR), check=False)
        status = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=str(SKILL_DIR),
        )
        if status.returncode == 0:
            subprocess.run(["git", "checkout", current], cwd=str(SKILL_DIR), check=False)
            return False
        subprocess.run(["git", "commit", "-m", msg], cwd=str(SKILL_DIR), check=True)
        subprocess.run(["git", "push", "-u", "origin", target], cwd=str(SKILL_DIR), check=True)
        subprocess.run(["git", "checkout", current], cwd=str(SKILL_DIR), check=False)
        return True
    except subprocess.CalledProcessError:
        subprocess.run(["git", "checkout", current or target], cwd=str(SKILL_DIR), check=False)
        return False
