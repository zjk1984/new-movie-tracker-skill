#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Send scan / download summaries to Feishu (Lark) via tenant app."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
import requests

SKILL_DIR = Path(__file__).resolve().parent.parent
FEISHU_API = "https://open.feishu.cn/open-apis"
TOKEN_CACHE: dict[str, Any] = {"token": "", "expires_at": 0.0}

FORUM_LABELS = {
    "forum-2": "forum-2 综合",
    "forum-95": "forum-95 国产",
    "forum-142": "forum-142 有码",
    "forum-103": "forum-103 有码",
    "forum-37": "forum-37 无码",
}

from env_utils import beijing_now, beijing_now_iso, format_beijing_time, load_env_local


def resolve_app_credentials() -> tuple[str, str]:
    app_id = (os.environ.get("FEISHU_APP_ID") or "").strip()
    app_secret = (os.environ.get("FEISHU_APP_SECRET") or "").strip()
    if not app_id or not app_secret:
        raise RuntimeError(
            "missing FEISHU_APP_ID / FEISHU_APP_SECRET in .env.local or environment"
        )
    return app_id, app_secret


def resolve_receive_target() -> tuple[str, str]:
    receive_id = (os.environ.get("FEISHU_RECEIVE_ID") or "").strip()
    if not receive_id:
        raise RuntimeError(
            "missing FEISHU_RECEIVE_ID (chat_id / open_id / user_id of target chat)"
        )
    receive_id_type = (os.environ.get("FEISHU_RECEIVE_ID_TYPE") or "chat_id").strip()
    return receive_id, receive_id_type


def get_tenant_access_token(*, force: bool = False) -> str:
    now = time.time()
    cached = TOKEN_CACHE.get("token") or ""
    if cached and not force and now < float(TOKEN_CACHE.get("expires_at") or 0):
        return cached

    app_id, app_secret = resolve_app_credentials()
    resp = requests.post(
        f"{FEISHU_API}/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"feishu token error: {data.get('msg') or data}")

    token = data["tenant_access_token"]
    expire = int(data.get("expire") or 7200)
    TOKEN_CACHE["token"] = token
    TOKEN_CACHE["expires_at"] = now + max(expire - 120, 60)
    return token


def send_message(
    msg_type: str,
    content: dict[str, Any] | str,
    *,
    receive_id: str | None = None,
    receive_id_type: str | None = None,
) -> dict[str, Any]:
    rid, rid_type = resolve_receive_target()
    if receive_id:
        rid = receive_id
    if receive_id_type:
        rid_type = receive_id_type

    token = get_tenant_access_token()
    if isinstance(content, dict):
        content_str = json.dumps(content, ensure_ascii=False)
    else:
        content_str = content

    body = {
        "receive_id": rid,
        "msg_type": msg_type,
        "content": content_str if msg_type == "interactive" else content_str,
    }
    if msg_type == "text":
        body["content"] = json.dumps({"text": content_str}, ensure_ascii=False)

    resp = requests.post(
        f"{FEISHU_API}/im/v1/messages",
        params={"receive_id_type": rid_type},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json=body,
        timeout=20,
    )
    data = resp.json()
    if resp.status_code >= 400 or data.get("code") not in (0, None):
        raise RuntimeError(f"feishu send failed: HTTP {resp.status_code} {data}")
    return data


def send_text(text: str, **kwargs: Any) -> dict[str, Any]:
    return send_message("text", text, **kwargs)


def send_interactive_card(card: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    return send_message("interactive", card, **kwargs)


def _forum_key(forum_url: str) -> str:
    match = re.search(r"forum-(\d+)", forum_url or "")
    return f"forum-{match.group(1)}" if match else "unknown"


def _forum_label(forum_url: str) -> str:
    key = _forum_key(forum_url)
    return FORUM_LABELS.get(key, key)


def _link_type(uri: str) -> str:
    u = (uri or "").lower()
    if u.startswith("magnet:"):
        return "magnet"
    if u.startswith("ed2k:"):
        return "ed2k"
    if u.startswith("pikpak:"):
        return "pikpak_sha"
    return "url"


def _is_bt_post(item: dict[str, Any]) -> bool:
    title = item.get("title") or ""
    if "BT种子" in title or "【BT" in title or "[BT" in title:
        return True
    for entry in item.get("hash_entries") or []:
        if entry.get("kind") == "hash_label_btih":
            return True
    return False


def _count_links(item: dict[str, Any]) -> dict[str, int]:
    mags = list(item.get("magnets") or [])
    if item.get("selected_magnet") and item["selected_magnet"] not in mags:
        mags.append(item["selected_magnet"])
    ed2k = list(item.get("ed2k") or [])
    if item.get("selected_ed2k") and item["selected_ed2k"] not in ed2k:
        ed2k.append(item["selected_ed2k"])
    bt = 0
    if _is_bt_post(item):
        bt = max(
            len([e for e in (item.get("hash_entries") or []) if e.get("kind") == "hash_label_btih"]),
            len(mags),
            1,
        )
    return {
        "magnet": len(mags),
        "ed2k": len(ed2k),
        "bt": bt,
    }


def _load_matched_paths(paths: list[Path]) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    seen_href: set[str] = set()
    for path in paths:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("matched") or data.get("threads") or []
        for item in items:
            href = item.get("href") or ""
            if href and href in seen_href:
                continue
            if href:
                seen_href.add(href)
            matched.append(item)
    return matched


def analyze_scan(
    result_paths: list[Path],
    *,
    ed2k_refetch_path: Path | None = None,
    enrich_javdb: bool = False,
) -> dict[str, Any]:
    sys.path.insert(0, str(SKILL_DIR / "scripts"))
    from content_filter import apply_region_filter, is_downloadable

    matched = _load_matched_paths(result_paths)
    scan_times: list[str] = []
    batch_mode = False
    for path in result_paths:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("scan_time"):
                scan_times.append(data["scan_time"])
            if data.get("batch_mode"):
                batch_mode = True

    # Merge ed2k from refetch by href
    ed2k_by_href: dict[str, list[str]] = {}
    if ed2k_refetch_path and ed2k_refetch_path.exists():
        refetch = json.loads(ed2k_refetch_path.read_text(encoding="utf-8"))
        for t in refetch.get("threads") or []:
            href = t.get("href") or ""
            if href and t.get("ed2k"):
                ed2k_by_href[href] = list(t["ed2k"])

    for item in matched:
        apply_region_filter(item, region_filter=True)
        href = item.get("href") or ""
        if href in ed2k_by_href:
            item["ed2k"] = ed2k_by_href[href]

    forums: Counter[str] = Counter()
    region_counts: Counter[str] = Counter()
    subtype_counts: Counter[str] = Counter()
    link_totals = {"magnet": 0, "ed2k": 0, "bt": 0}
    posts_with = {"magnet": 0, "ed2k": 0, "bt": 0}
    downloadable = 0

    javdb_summary: dict[str, Any] = {}
    if enrich_javdb:
        from javdb_client import enrich_matched_javdb, is_submit_eligible

        javdb_summary = enrich_matched_javdb(matched)
        for item in matched:
            is_submit_eligible(item, query_if_missing=False)

    with_link = 0
    without_link = 0
    skipped_jav_score = 0
    from pikpak_download import pick_item_download

    from scan import item_forum_urls

    for item in matched:
        urls = item_forum_urls(item)
        if not urls:
            forums["unknown"] += 1
        else:
            for forum_url in urls:
                forums[_forum_label(forum_url)] += 1
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
        for k in link_totals:
            link_totals[k] += counts[k]
            if counts[k] > 0:
                posts_with[k] += 1

    if javdb_summary:
        javdb_summary["skipped_low_score"] = skipped_jav_score

    return {
        "scan_time": max(scan_times) if scan_times else beijing_now_iso(),
        "forums": dict(forums),
        "matched_total": len(matched),
        "downloadable": downloadable,
        "with_link": with_link,
        "without_link": without_link,
        "region_counts": dict(region_counts),
        "subtype_counts": dict(subtype_counts),
        "link_totals": link_totals,
        "posts_with": posts_with,
        "matched": matched,
        "javdb_summary": javdb_summary,
        "skipped_jav_score": skipped_jav_score,
        "batch_mode": batch_mode,
    }


def load_download_report(path: Path | None) -> dict[str, Any]:
    if path and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"succeeded": [], "failed": [], "ok": 0, "failed_count": 0, "total": 0}


def _truncate(text: str, limit: int = 80) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _error_summary(failed: list[dict]) -> str:
    buckets: Counter[str] = Counter()
    for item in failed:
        err = item.get("error") or "unknown"
        if "task_url_resolve_error" in err:
            buckets["ed2k/URL 解析失败 (PikPak 不支持或链接无效)"] += 1
        elif "not in PikPak cache" in err:
            buckets["特征码秒传失败 (PikPak 无缓存)"] += 1
        elif "HTTP 4" in err:
            buckets["API 请求失败"] += 1
        else:
            buckets[_truncate(err, 60)] += 1
    if not buckets:
        return "无"
    return "\n".join(f"• {reason}: **{count}**" for reason, count in buckets.most_common(6))


def _submit_funnel_card_lines(scan_stats: dict[str, Any]) -> str:
    sf = scan_stats.get("submit_funnel") or {}
    if not sf:
        return ""
    multi = sf.get("multi_link_posts", 0)
    multi_text = f"（**{multi}** 帖含多条）" if multi else ""
    return (
        f"5a. 待提交链接（展开）: **{sf.get('expanded_links', 0)}** 条{multi_text}\n"
        f"5b. 扫描去重后: **{sf.get('submit_candidates', 0)}** 条"
        f"（跳过旧扫描 **{sf.get('scan_dedup_skipped', 0)}** 条）\n"
        f"5c. new_only 跳过: **{sf.get('new_only_skipped', 0)}** 条（已在 download_state）\n"
    )


def _submit_funnel_footnote(
    scan_stats: dict[str, Any],
    link_sum: int,
    total: int,
) -> str:
    sf = scan_stats.get("submit_funnel") or {}
    if sf:
        return (
            f"_有链接帖展开 **{sf.get('expanded_links', 0)}** 条 URI → "
            f"扫描去重 **{sf.get('submit_candidates', 0)}** → "
            f"new_only 跳过 **{sf.get('new_only_skipped', 0)}** → "
            f"本次提交 **{total}** 条_"
        )
    return f"_{link_sum} 条 URI ≠ {total} 条提交：内容过滤 + 无链接 + JavDB 门控 + 去重_"


def build_scan_summary_card(
    scan_stats: dict[str, Any],
    download_report: dict[str, Any],
    *,
    report_url: str | None = None,
) -> dict[str, Any]:
    forums = scan_stats.get("forums") or {}
    forum_lines = "\n".join(f"• {name}: **{count}** 帖" for name, count in sorted(forums.items()))
    lt = scan_stats.get("link_totals") or {}
    pw = scan_stats.get("posts_with") or {}

    ok = download_report.get("ok", 0)
    fail = download_report.get("failed_count", 0)
    total = download_report.get("total") or (ok + fail)

    dl_posts = scan_stats.get("downloadable", 0)
    with_link = scan_stats.get("with_link", 0)
    without_link = scan_stats.get("without_link", 0)
    jav = scan_stats.get("javdb_summary") or {}
    subtype = scan_stats.get("subtype_counts") or {}

    skipped_score = scan_stats.get("skipped_jav_score", 0)
    jav_lines = ""
    if jav.get("total"):
        avg = jav.get("avg_score")
        avg_text = f"{avg:.2f}" if avg is not None else "-"
        jav_lines = (
            f"\n**日本片 JavDB** 共 **{jav.get('total', 0)}** 帖"
            f" | 已查 **{jav.get('queried', 0)}**"
            f" | 含中字 **{jav.get('with_cnsub', 0)}**"
            f" | 均分 **{avg_text}**"
            f" | 低分/无分跳过 **{skipped_score or jav.get('skipped_low_score', 0)}**\n"
        )
    domestic_lines = ""
    if subtype:
        sub_text = " | ".join(f"{k} {v}" for k, v in sorted(subtype.items(), key=lambda x: -x[1]))
        domestic_lines = f"\n**国产子类** {sub_text}\n"

    repeat = scan_stats.get("matched_repeat") or 0
    repeat_line = (
        f"（相对上次扫描隐藏重复 **{repeat}** 条，仅展示新增）\n"
        if repeat
        else ""
    )
    link_sum = lt.get("magnet", 0) + lt.get("ed2k", 0) + lt.get("bt", 0)
    md = (
        f"**扫描时间** {format_beijing_time(scan_stats.get('scan_time')) or '（无）'}\n\n"
        f"**扫描板块**\n{forum_lines or '(无)'}\n\n"
        f"**数据漏斗**{repeat_line}\n"
        f"1. 匹配帖: **{scan_stats.get('matched_total', 0)}**\n"
        f"2. 采集链接合计: **{link_sum}** 条 URI"
        f"（磁力 **{lt.get('magnet', 0)}** / ed2k **{lt.get('ed2k', 0)}** / BT **{lt.get('bt', 0)}**）\n"
        f"3. 可下载(过滤): **{dl_posts}** 帖\n"
        f"4. 有链接: **{with_link}** 帖 | 无链接: **{without_link}** 帖\n"
        f"5. JavDB 低分/无分: **{skipped_score}** 帖\n"
        f"{_submit_funnel_card_lines(scan_stats)}"
        f"6. PikPak 提交: 成功 **{ok}** + 失败 **{fail}** = **{total}** 条（按链接计）\n"
        f"{_submit_funnel_footnote(scan_stats, link_sum, total)}\n"
        f"{jav_lines}{domestic_lines}\n"
        f"**失败原因汇总**\n{_error_summary(download_report.get('failed') or [])}\n"
    )
    if report_url:
        md += f"\n**完整报告**: [查看 Markdown 报告]({report_url})"

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "📊 论坛扫描总结"},
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": md}},
        ],
    }


def _prepare_notify_payload(
    result_paths: list[Path],
    *,
    download_report_path: Path | None = None,
    extra_download_reports: list[Path] | None = None,
    ed2k_refetch_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    from run_report import merge_download_reports

    scan_stats = analyze_scan(
        result_paths,
        ed2k_refetch_path=ed2k_refetch_path,
        enrich_javdb=True,
    )
    download_report = load_download_report(download_report_path)
    merge_paths = [p for p in (extra_download_reports or []) if p and p.exists()]
    extras = [load_download_report(p) for p in merge_paths]
    if extras:
        download_report = merge_download_reports(download_report, *extras)
        print(
            f"[info] merged download reports: ok={download_report.get('ok')} "
            f"fail={download_report.get('failed_count')}"
        )
    elif not (download_report.get("succeeded") or download_report.get("failed")):
        print(
            "[warn] download report empty; pass --download-report and/or "
            "--bt-download-report with real submit results"
        )

    from javdb_client import filter_download_report_by_jav_score
    from scan_delta import apply_scan_dedup, compute_submit_funnel_stats

    download_report = filter_download_report_by_jav_score(
        download_report,
        scan_stats.get("matched") or [],
    )

    output_dir = result_paths[0].parent if result_paths else SKILL_DIR / "data"
    scan_stats, download_report = apply_scan_dedup(
        scan_stats,
        download_report,
        output_dir=output_dir,
    )
    if result_paths:
        try:
            scan_stats["submit_funnel"] = compute_submit_funnel_stats(
                scan_stats.get("matched") or [],
                download_report,
                result_path=result_paths[0],
                output_dir=output_dir,
            )
        except Exception as exc:
            print(f"[warn] submit funnel stats: {exc}")
    repeat = scan_stats.get("matched_repeat") or 0
    if repeat:
        print(
            f"[info] scan dedup: hid {repeat} item(s) already in previous scan; "
            f"showing {scan_stats.get('matched_total', 0)} new",
        )
    return scan_stats, download_report, output_dir


def _push_report_and_url(
    report_path: Path,
    *,
    push_report: bool,
    archived_paths: list[Path] | None = None,
) -> str | None:
    from run_report import commit_and_push_report, github_blob_url, report_github_branch

    rel = report_path.relative_to(SKILL_DIR)
    report_url: str | None = None
    if push_report:
        if commit_and_push_report(
            report_path,
            archived_paths=archived_paths or [],
        ):
            report_url = github_blob_url(str(rel), branch=report_github_branch())
            print(f"[ok] report pushed: {rel}")
            if archived_paths:
                print(
                    f"[info] archived {len(archived_paths)} report(s) "
                    f"to reports/backup/",
                )
        else:
            print(
                f"[warn] report saved locally but not on GitHub; "
                f"Feishu card will omit broken link: {rel}",
            )
    else:
        print(f"[info] report saved locally only (--no-push): {rel}")
    return report_url


def notify_cards(
    result_paths: list[Path],
    *,
    download_report_path: Path | None = None,
    extra_download_reports: list[Path] | None = None,
    ed2k_refetch_path: Path | None = None,
    push_report: bool = True,
    run_label: str = "scan",
    existing_report_path: Path | None = None,
) -> tuple[list[dict[str, Any]], Path, str | None]:
    from run_report import write_run_report

    scan_stats, download_report, output_dir = _prepare_notify_payload(
        result_paths,
        download_report_path=download_report_path,
        extra_download_reports=extra_download_reports,
        ed2k_refetch_path=ed2k_refetch_path,
    )

    if existing_report_path is not None:
        report_path = existing_report_path.resolve()
        archived_paths: list[Path] = []
    else:
        report_result = write_run_report(
            scan_stats,
            download_report,
            run_label=run_label,
            output_dir=output_dir,
        )
        report_path = report_result.path
        archived_paths = report_result.archived_paths

    report_url = _push_report_and_url(
        report_path,
        push_report=push_report,
        archived_paths=archived_paths,
    )

    card = build_scan_summary_card(scan_stats, download_report, report_url=report_url)
    result = send_interactive_card(card)
    return [result], report_path, report_url


def notify_scan_result(
    result_path: Path,
    *,
    push_report: bool = True,
) -> dict[str, Any]:
    results, _, _ = notify_cards([result_path], push_report=push_report)
    return results[0]


def is_configured() -> bool:
    try:
        resolve_app_credentials()
        resolve_receive_target()
        return True
    except RuntimeError:
        return False


def build_scan_start_card(
    *,
    run_label: str = "扫描",
    forum_urls: list[str] | None = None,
    start_page: int = 1,
    max_pages: int = 1,
    days: int | None = None,
    no_date_filter: bool = False,
) -> dict[str, Any]:
    forums = forum_urls or []
    forum_lines = "\n".join(
        f"• {_forum_label(url)}" for url in forums
    ) or "• （无）"
    end_page = start_page + max_pages - 1
    if no_date_filter:
        range_line = f"页码 **{start_page} ~ {end_page}**（共 **{max_pages}** 页）| 日期 **不限**"
    elif days is not None:
        range_line = (
            f"页码 **1 ~ {max_pages}**（最多 **{max_pages}** 页）"
            f" | 最近 **{days}** 天"
        )
    else:
        range_line = f"页码 **{start_page} ~ {end_page}**（共 **{max_pages}** 页）"

    task_name = _run_label_title(run_label)

    md = (
        f"**开始时间** {format_beijing_time(beijing_now(), with_label=True)}\n\n"
        f"**任务类型** {task_name}\n\n"
        f"**扫描板块**\n{forum_lines}\n\n"
        f"**扫描范围**\n• {range_line}\n\n"
        f"**进度通知** 每 **100** 帖推送一次；完成后发送总结报告"
    )
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "green",
            "title": {"tag": "plain_text", "content": "🚀 扫描已开始"},
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": md}},
        ],
    }


def send_scan_start(
    *,
    run_label: str = "scan",
    forum_urls: list[str] | None = None,
    start_page: int = 1,
    max_pages: int = 1,
    days: int | None = None,
    no_date_filter: bool = False,
) -> dict[str, Any] | None:
    if not is_configured():
        return None
    card = build_scan_start_card(
        run_label=run_label,
        forum_urls=forum_urls,
        start_page=start_page,
        max_pages=max_pages,
        days=days,
        no_date_filter=no_date_filter,
    )
    return send_interactive_card(card)


def _run_label_title(run_label: str) -> str:
    title_map = {
        "daily": "日常扫描",
        "custom": "自定义扫描",
        "scan": "论坛扫描",
        "forum-142": "forum-142 批量扫描",
        "forum-37": "forum-37 批量扫描",
    }
    return title_map.get(run_label, run_label or "论坛扫描")


def build_scan_done_card(
    scan_stats: dict[str, Any],
    *,
    run_label: str = "scan",
) -> dict[str, Any]:
    forums = scan_stats.get("forums") or {}
    forum_lines = "\n".join(
        f"• {name}: **{count}** 帖" for name, count in sorted(forums.items())
    ) or "• （无）"
    lt = scan_stats.get("link_totals") or {}
    pw = scan_stats.get("posts_with") or {}
    link_sum = lt.get("magnet", 0) + lt.get("ed2k", 0) + lt.get("bt", 0)
    md = (
        f"**完成时间** {format_beijing_time(beijing_now(), with_label=True)}\n\n"
        f"**任务类型** {_run_label_title(run_label)}\n\n"
        f"**扫描板块**\n{forum_lines}\n\n"
        f"**数据漏斗（扫描阶段）**\n"
        f"1. 匹配帖: **{scan_stats.get('matched_total', 0)}**\n"
        f"2. 采集链接: **{link_sum}** 条 URI\n"
        f"3. 可下载: **{scan_stats.get('downloadable', 0)}** 帖\n"
        f"4. 有链接: **{scan_stats.get('with_link', 0)}** 帖"
        f" | 无链接: **{scan_stats.get('without_link', 0)}** 帖\n\n"
        f"**下一步** PikPak 提交进行中（若未跳过下载）"
    )
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "orange",
            "title": {"tag": "plain_text", "content": "✅ 扫描完成"},
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": md}},
        ],
    }


def build_pikpak_done_card(
    download_report: dict[str, Any],
    *,
    run_label: str = "scan",
) -> dict[str, Any]:
    ok = int(download_report.get("ok") or 0)
    fail = int(download_report.get("failed_count") or 0)
    total = int(download_report.get("total") or (ok + fail))
    md = (
        f"**完成时间** {format_beijing_time(beijing_now(), with_label=True)}\n\n"
        f"**任务类型** {_run_label_title(run_label)}\n\n"
        f"**PikPak 提交结果**（按链接计）\n"
        f"• 成功: **{ok}**\n"
        f"• 失败: **{fail}**\n"
        f"• 合计: **{total}**\n\n"
    )
    if fail:
        md += f"**失败原因**\n{_error_summary(download_report.get('failed') or [])}\n\n"
    md += "**下一步** 正在生成完整 Markdown 报告并推送"
    template = "green" if fail == 0 else "yellow"
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": template,
            "title": {"tag": "plain_text", "content": "✅ PikPak 提交完成"},
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": md}},
        ],
    }


def send_scan_done(
    result_path: Path,
    *,
    run_label: str = "scan",
) -> dict[str, Any] | None:
    if not is_configured() or not result_path.exists():
        return None
    scan_stats = analyze_scan([result_path], enrich_javdb=False)
    return send_interactive_card(build_scan_done_card(scan_stats, run_label=run_label))


def send_pikpak_done(
    download_report_path: Path,
    *,
    run_label: str = "scan",
    pikpak_ok: int | None = None,
    pikpak_total: int | None = None,
) -> dict[str, Any] | None:
    if not is_configured():
        return None
    report = load_download_report(download_report_path if download_report_path.exists() else None)
    if pikpak_ok is not None:
        report["ok"] = pikpak_ok
    if pikpak_total is not None:
        report["total"] = pikpak_total
        report["failed_count"] = max(0, pikpak_total - int(report.get("ok") or 0))
    return send_interactive_card(build_pikpak_done_card(report, run_label=run_label))


def send_scan_progress(
    matched_count: int,
    *,
    forum_url: str = "",
    page_num: int | None = None,
    page_range: str | None = None,
    run_label: str = "扫描",
) -> dict[str, Any] | None:
    """Notify Feishu every N matched posts during a long scan."""
    if not is_configured():
        return None
    forum = _forum_label(forum_url) if forum_url else "未知"
    lines = [
        f"【{run_label}进度】已匹配 {matched_count} 帖",
        f"板块: {forum}",
    ]
    if page_num is not None:
        lines.append(f"当前页: {page_num}")
    if page_range:
        lines.append(f"页码范围: {page_range}")
    lines.append(f"时间: {format_beijing_time(beijing_now(), with_label=False)}")
    return send_text("\n".join(lines))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    load_env_local()
    parser = argparse.ArgumentParser(description="Send Feishu notifications for scan results")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ping = sub.add_parser("ping", help="Verify app credentials")
    ping.set_defaults(func="ping")

    send = sub.add_parser("send", help="Send a plain text message")
    send.add_argument("text", help="Message body")
    send.set_defaults(func="send")

    summary = sub.add_parser("summary", help="Send Feishu summary card (+ MD report)")
    summary.add_argument("--input", default=str(SKILL_DIR / "last_result.json"))
    summary.add_argument("--no-push", action="store_true")
    summary.set_defaults(func="summary")

    cards = sub.add_parser("cards", help="Write MD report, push to GitHub, send Feishu summary")
    cards.add_argument(
        "--input",
        action="append",
        default=[],
        help="Scan result JSON (repeatable)",
    )
    cards.add_argument(
        "--ed2k-refetch",
        default=str(SKILL_DIR / "scan-ed2k-refetch/refetch_result.json"),
        help="ed2k refetch JSON",
    )
    cards.add_argument(
        "--download-report",
        default=str(SKILL_DIR / "data/download_report.json"),
        help="download_report.json from pikpak_download",
    )
    cards.add_argument(
        "--bt-download-report",
        default=str(SKILL_DIR / "scan-bt-refetch/download_report.json"),
        help="BT refetch submit report (merged into success list)",
    )
    cards.add_argument(
        "--no-push",
        action="store_true",
        help="Save report locally without git commit/push",
    )
    cards.add_argument("--run-label", default="scan", help="Report filename prefix")
    cards.set_defaults(func="cards")

    args = parser.parse_args()

    try:
        if args.func == "ping":
            token = get_tenant_access_token(force=True)
            print(f"[ok] tenant_access_token acquired ({token[:12]}...)")
            if os.environ.get("FEISHU_RECEIVE_ID"):
                send_text("飞书通知测试 OK")
                print("[ok] test message sent")
            else:
                print("[info] FEISHU_RECEIVE_ID not set — token OK, skipping send")
            return 0

        if args.func == "send":
            send_text(args.text)
            print("[ok] message sent")
            return 0

        if args.func == "summary":
            _, report_path, report_url = notify_cards(
                [Path(args.input)],
                push_report=not args.no_push,
            )
            print(f"[ok] summary sent; report: {report_path}")
            if report_url:
                print(f"[ok] github: {report_url}")
            return 0

        if args.func == "cards":
            inputs = args.input or [
                str(SKILL_DIR / "scan-forum-95-142-today/last_result.json"),
                str(SKILL_DIR / "scan-today-f37-f103/last_result.json"),
            ]
            extra_reports = []
            if args.bt_download_report:
                extra_reports.append(Path(args.bt_download_report))
            dl_report = Path(args.download_report)
            _, report_path, report_url = notify_cards(
                [Path(p) for p in inputs],
                download_report_path=dl_report if dl_report.exists() else None,
                extra_download_reports=extra_reports,
                ed2k_refetch_path=Path(args.ed2k_refetch) if args.ed2k_refetch else None,
                push_report=not args.no_push,
                run_label=args.run_label,
            )
            print(f"[ok] summary sent; report: {report_path}")
            if report_url:
                print(f"[ok] github: {report_url}")
            return 0
    except Exception as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
