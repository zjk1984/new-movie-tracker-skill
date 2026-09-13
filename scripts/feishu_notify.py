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

REGION_LABELS = {
    "jav_censored": "日本有码",
    "uncensored": "无码破解",
    "domestic_leak": "国产保留",
    "domestic_other": "国产其他(排除)",
    "western": "欧美(排除)",
    "fc2": "FC2(排除)",
    "amateur": "素人(排除)",
    "other": "其他(排除)",
}

DOMESTIC_SUBTYPE_LABELS = {
    "泄密": "泄密",
    "流出": "流出",
    "AI增强": "AI增强",
    "AI短剧": "AI短剧",
    "熟女自拍": "熟女自拍",
    "酒店偷拍": "酒店偷拍",
    "ed2k": "ed2k",
}

CATEGORY_HELP = (
    "**分类说明**\n"
    "• **日本有码**：带番号有码 JAV，默认下载\n"
    "• **无码破解**：无码/破解 JAV\n"
    "• **国产保留**：泄密/流出/AI增强/AI短剧/熟女/酒店偷拍/ed2k\n"
    "• **已排除**：欧美、FC2、素人、私拍、伪番号、OnlyFans 等"
)


def load_env_local(skill_dir: Path | None = None) -> None:
    env_path = (skill_dir or SKILL_DIR) / ".env.local"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


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
) -> dict[str, Any]:
    sys.path.insert(0, str(SKILL_DIR / "scripts"))
    from content_filter import apply_region_filter, is_downloadable

    matched = _load_matched_paths(result_paths)
    scan_times: list[str] = []
    for path in result_paths:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("scan_time"):
                scan_times.append(data["scan_time"])

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

    for item in matched:
        forums[_forum_label(item.get("forum", ""))] += 1
        region = item.get("content_region") or "other"
        region_counts[region] += 1
        sub = item.get("domestic_subtype")
        if sub:
            subtype_counts[sub] += 1
        if is_downloadable(item):
            downloadable += 1
        counts = _count_links(item)
        for k in link_totals:
            link_totals[k] += counts[k]
            if counts[k] > 0:
                posts_with[k] += 1

    return {
        "scan_time": max(scan_times) if scan_times else datetime.now().isoformat(timespec="seconds"),
        "forums": dict(forums),
        "matched_total": len(matched),
        "downloadable": downloadable,
        "region_counts": dict(region_counts),
        "subtype_counts": dict(subtype_counts),
        "link_totals": link_totals,
        "posts_with": posts_with,
        "matched": matched,
    }


def load_download_report(path: Path | None) -> dict[str, Any]:
    if path and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"succeeded": [], "failed": [], "ok": 0, "failed_count": 0, "total": 0}


def build_download_report_from_scans(
    result_paths: list[Path],
    *,
    ed2k_refetch_path: Path | None = None,
    ed2k_error: str = "task_url_resolve_error: PikPak 无法解析 ed2k 链接",
) -> dict[str, Any]:
    """Rebuild download report when only scan + ed2k refetch data exist."""
    sys.path.insert(0, str(SKILL_DIR / "scripts"))
    from content_filter import is_downloadable
    from pikpak_download import item_download_name, pick_item_download

    stats = analyze_scan(result_paths, ed2k_refetch_path=ed2k_refetch_path)
    succeeded: list[dict] = []
    failed: list[dict] = []

    submit_summary = SKILL_DIR / "data" / "submit_summary.json"
    magnet_ok = 0
    if submit_summary.exists():
        s = json.loads(submit_summary.read_text(encoding="utf-8"))
        magnet_ok = int(s.get("grand_ok", 0)) - int((s.get("ed2k") or {}).get("ok", 0))

    magnet_added = 0
    for item in stats["matched"]:
        if not is_downloadable(item):
            continue
        dl = pick_item_download(item)
        if not dl:
            continue
        uri = dl.get("uri") or dl.get("url") or ""
        ltype = _link_type(uri)
        if ltype == "ed2k":
            failed.append({
                "name": dl.get("name") or item_download_name(item),
                "title": item.get("title", ""),
                "href": item.get("href", ""),
                "uri": uri,
                "url": uri,
                "link_type": "ed2k",
                "source": dl.get("source", "forum_ed2k"),
                "status": "failed",
                "error": ed2k_error,
            })
            continue
        if ltype == "magnet" and magnet_added < magnet_ok:
            succeeded.append({
                "name": dl.get("name") or item_download_name(item),
                "title": item.get("title", ""),
                "href": item.get("href", ""),
                "uri": uri,
                "url": uri,
                "link_type": "magnet",
                "source": dl.get("source", ""),
                "status": "ok",
                "phase": "PHASE_TYPE_RUNNING",
            })
            magnet_added += 1

    # Extra ed2k URIs from refetch (multi-file posts)
    if ed2k_refetch_path and ed2k_refetch_path.exists():
        from pikpak_links import parse_download_link

        refetch = json.loads(ed2k_refetch_path.read_text(encoding="utf-8"))
        seen_uri = {x.get("uri") for x in failed}
        for t in refetch.get("threads") or []:
            for ed2k in t.get("ed2k") or []:
                if ed2k in seen_uri:
                    continue
                parsed = parse_download_link(ed2k)
                if not parsed:
                    continue
                failed.append({
                    "name": parsed.get("name") or "ed2k",
                    "title": t.get("title", ""),
                    "href": t.get("href", ""),
                    "uri": ed2k,
                    "url": ed2k,
                    "link_type": "ed2k",
                    "source": "forum_ed2k",
                    "status": "failed",
                    "error": ed2k_error,
                })
                seen_uri.add(ed2k)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ok": len(succeeded),
        "failed_count": len(failed),
        "total": len(succeeded) + len(failed),
        "succeeded": succeeded,
        "failed": failed,
        "reconstructed": True,
    }


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


def _md_item_lines(items: list[dict], *, max_items: int = 8) -> list[str]:
    lines: list[str] = []
    for item in items[:max_items]:
        name = _truncate(item.get("name") or item.get("av_number") or "?", 50)
        ltype = item.get("link_type") or _link_type(item.get("uri") or item.get("url") or "")
        uri = item.get("uri") or item.get("url") or ""
        title = _truncate(item.get("title") or "", 55)
        lines.append(f"**{name}** `[{ltype}]`")
        if title:
            lines.append(f"  {title}")
        if uri:
            lines.append(f"  `{_truncate(uri, 100)}`")
        if item.get("error"):
            lines.append(f"  ❌ {_truncate(item['error'], 90)}")
        elif item.get("phase"):
            lines.append(f"  ✅ {item.get('phase')}")
    if len(items) > max_items:
        lines.append(f"\n… 另有 **{len(items) - max_items}** 条")
    return lines


def build_scan_summary_card(
    scan_stats: dict[str, Any],
    download_report: dict[str, Any],
) -> dict[str, Any]:
    forums = scan_stats.get("forums") or {}
    forum_lines = "\n".join(f"• {name}: **{count}** 帖" for name, count in sorted(forums.items()))
    lt = scan_stats.get("link_totals") or {}
    pw = scan_stats.get("posts_with") or {}
    rc = scan_stats.get("region_counts") or {}
    sc = scan_stats.get("subtype_counts") or {}

    region_lines = "\n".join(
        f"• {REGION_LABELS.get(k, k)}: **{v}**"
        for k, v in sorted(rc.items(), key=lambda x: -x[1])
        if v > 0
    )
    subtype_lines = ""
    if sc:
        subtype_lines = "\n**国产子类**\n" + "\n".join(
            f"• {DOMESTIC_SUBTYPE_LABELS.get(k, k)}: **{v}**"
            for k, v in sorted(sc.items(), key=lambda x: -x[1])
        )

    ok = download_report.get("ok", 0)
    fail = download_report.get("failed_count", 0)
    total = download_report.get("total") or (ok + fail)

    md = (
        f"**扫描时间** {str(scan_stats.get('scan_time', ''))[:19]}\n\n"
        f"**扫描板块**\n{forum_lines or '(无)'}\n\n"
        f"**帖子统计** 共 **{scan_stats.get('matched_total', 0)}** 帖 | "
        f"可下载 **{scan_stats.get('downloadable', 0)}**\n\n"
        f"**链接采集**\n"
        f"• 磁力: **{lt.get('magnet', 0)}** 条 ({pw.get('magnet', 0)} 帖)\n"
        f"• ed2k: **{lt.get('ed2k', 0)}** 条 ({pw.get('ed2k', 0)} 帖)\n"
        f"• BT种子: **{lt.get('bt', 0)}** 条 ({pw.get('bt', 0)} 帖)\n\n"
        f"**PikPak 提交** 成功 **{ok}** / 失败 **{fail}** / 共 **{total}**\n\n"
        f"**失败原因汇总**\n{_error_summary(download_report.get('failed') or [])}\n\n"
        f"**帖子分类**\n{region_lines or '(无)'}"
        f"{subtype_lines}\n\n"
        f"{CATEGORY_HELP}"
    )

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


def build_download_success_card(download_report: dict[str, Any]) -> dict[str, Any]:
    items = download_report.get("succeeded") or []
    by_type = Counter(_link_type(x.get("uri") or x.get("url") or "") for x in items)
    type_line = " | ".join(f"{k} **{v}**" for k, v in by_type.items()) if by_type else "无"

    lines = [f"共 **{len(items)}** 条成功提交到 My Pack", f"类型: {type_line}", ""]
    lines.extend(_md_item_lines(items, max_items=10))

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "green",
            "title": {"tag": "plain_text", "content": "✅ 下载成功"},
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines) or "暂无成功记录"}},
        ],
    }


def build_download_fail_card(download_report: dict[str, Any]) -> dict[str, Any]:
    items = download_report.get("failed") or []
    lines = [
        f"共 **{len(items)}** 条提交失败",
        "",
        "**失败原因汇总**",
        _error_summary(items),
        "",
        "**失败明细**",
    ]
    lines.extend(_md_item_lines(items, max_items=10))

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "red",
            "title": {"tag": "plain_text", "content": "❌ 下载失败"},
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines) or "暂无失败记录"}},
        ],
    }


def notify_cards(
    result_paths: list[Path],
    *,
    download_report_path: Path | None = None,
    ed2k_refetch_path: Path | None = None,
    reconstruct_report: bool = False,
) -> list[dict[str, Any]]:
    scan_stats = analyze_scan(result_paths, ed2k_refetch_path=ed2k_refetch_path)
    if reconstruct_report or not (download_report_path and download_report_path.exists()):
        download_report = build_download_report_from_scans(
            result_paths, ed2k_refetch_path=ed2k_refetch_path,
        )
    else:
        download_report = load_download_report(download_report_path)

    cards = [
        build_scan_summary_card(scan_stats, download_report),
        build_download_fail_card(download_report),
        build_download_success_card(download_report),
    ]
    results = []
    for card in cards:
        results.append(send_interactive_card(card))
        time.sleep(0.3)
    return results


def format_scan_summary(
    result_path: Path,
    *,
    pikpak_ok: int | None = None,
    pikpak_total: int | None = None,
    extra_lines: list[str] | None = None,
) -> str:
    stats = analyze_scan([result_path])
    dl = {"ok": pikpak_ok or 0, "failed_count": (pikpak_total or 0) - (pikpak_ok or 0), "total": pikpak_total or 0, "failed": []}
    card = build_scan_summary_card(stats, dl)
    return card["elements"][0]["text"]["content"]


def notify_scan_result(
    result_path: Path,
    *,
    pikpak_ok: int | None = None,
    pikpak_total: int | None = None,
    extra_lines: list[str] | None = None,
) -> dict[str, Any]:
    return notify_cards([result_path], reconstruct_report=True)[0]


def is_configured() -> bool:
    try:
        resolve_app_credentials()
        resolve_receive_target()
        return True
    except RuntimeError:
        return False


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

    summary = sub.add_parser("summary", help="Send text summary from last_result.json")
    summary.add_argument("--input", default=str(SKILL_DIR / "last_result.json"))
    summary.add_argument("--pikpak-ok", type=int, default=None)
    summary.add_argument("--pikpak-total", type=int, default=None)
    summary.set_defaults(func="summary")

    cards = sub.add_parser("cards", help="Send 3 interactive cards: scan / fail / success")
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
        "--reconstruct",
        action="store_true",
        help="Rebuild download report from scan + submit_summary",
    )
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
            notify_scan_result(
                Path(args.input),
                pikpak_ok=args.pikpak_ok,
                pikpak_total=args.pikpak_total,
            )
            print("[ok] summary sent")
            return 0

        if args.func == "cards":
            inputs = args.input or [
                str(SKILL_DIR / "scan-forum-95-142-today/last_result.json"),
                str(SKILL_DIR / "scan-today-f37-f103/last_result.json"),
            ]
            notify_cards(
                [Path(p) for p in inputs],
                download_report_path=Path(args.download_report),
                ed2k_refetch_path=Path(args.ed2k_refetch) if args.ed2k_refetch else None,
                reconstruct_report=args.reconstruct or not Path(args.download_report).exists(),
            )
            print("[ok] 3 cards sent (scan summary / download fail / download success)")
            return 0
    except Exception as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
