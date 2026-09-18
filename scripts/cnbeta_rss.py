#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch CNBeta RSS feeds and push new items to Feishu."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import requests

from env_utils import beijing_now, format_beijing_time, load_env_local

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_FEEDS = ("https://rss.cnbeta.com.tw",)
DEFAULT_STATE_PATH = SKILL_DIR / "data" / "cnbeta_rss_state.json"
DEFAULT_UPDATE_DIR = SKILL_DIR / "update"
DEFAULT_MAX_ITEMS = 20
UPDATE_NAME_RE = re.compile(r"^(\d{8}-\d{6})(?:_\d+)?\.md$")
UPDATE_LINK_LINE_RE = re.compile(r"^\s*-\s*\*\*链接\*\*:\s*(\S+)\s*$", re.MULTILINE)
UPDATE_LINK_RE = re.compile(r"\[[^\]]*\]\((https?://[^)]+)\)")
UPDATE_ITEM_ID_RE = re.compile(r"<!--\s*item-id:\s*(.+?)\s*-->")
CATEGORY_LABELS = {
    "tech": "科技",
    "game": "游戏",
    "soft": "软件",
    "science": "科学",
    "movie": "影视",
    "music": "音乐",
    "misc": "趣闻",
}


@dataclass(frozen=True)
class NewsItem:
    item_id: str
    title: str
    link: str
    published: str
    category: str
    summary: str
    feed_url: str

    @property
    def category_label(self) -> str:
        return CATEGORY_LABELS.get(self.category, self.category or "资讯")


def resolve_feed_urls() -> list[str]:
    raw = (os.environ.get("CNBETA_RSS_FEEDS") or "").strip()
    if raw:
        return [part.strip() for part in raw.split(",") if part.strip()]
    return list(DEFAULT_FEEDS)


def resolve_state_path() -> Path:
    custom = (os.environ.get("CNBETA_RSS_STATE_PATH") or "").strip()
    return Path(custom) if custom else DEFAULT_STATE_PATH


def resolve_update_dir() -> Path:
    custom = (os.environ.get("CNBETA_RSS_UPDATE_DIR") or "").strip()
    return Path(custom) if custom else DEFAULT_UPDATE_DIR


def resolve_max_items() -> int:
    raw = (os.environ.get("CNBETA_RSS_MAX_ITEMS") or str(DEFAULT_MAX_ITEMS)).strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_ITEMS


def _update_sort_key(path: Path) -> tuple[str, str]:
    match = UPDATE_NAME_RE.match(path.name)
    if match:
        return match.group(1), path.name
    return str(path.stat().st_mtime), path.name


def list_update_md_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    files = [p for p in directory.glob("*.md") if p.is_file()]
    return sorted(files, key=_update_sort_key, reverse=True)


def find_latest_update_md(update_dir: Path) -> Path | None:
    files = list_update_md_files(update_dir)
    return files[0] if files else None


def parse_item_ids_from_update_md(path: Path) -> set[str]:
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8")
    ids: set[str] = set()
    for match in UPDATE_ITEM_ID_RE.finditer(text):
        ids.add(match.group(1).strip())
    for match in UPDATE_LINK_LINE_RE.finditer(text):
        ids.add(match.group(1).strip())
    if ids:
        return ids
    for match in UPDATE_LINK_RE.finditer(text):
        link = match.group(1).strip()
        if link:
            ids.add(link)
    return ids


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


def archive_update_to_backup(previous: Path, *, update_dir: Path) -> Path:
    backup_dir = update_dir / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = _unique_backup_dest(backup_dir, previous.name)
    previous.rename(dest)
    return dest


def update_filename_for_now() -> str:
    return beijing_now().strftime("%Y%m%d-%H%M%S") + ".md"


def _unique_update_dest(update_dir: Path, name: str) -> Path:
    dest = update_dir / name
    if not dest.exists():
        return dest
    stem = Path(name).stem
    suffix = Path(name).suffix
    n = 1
    while dest.exists():
        dest = update_dir / f"{stem}_{n}{suffix}"
        n += 1
    return dest


def build_update_markdown(
    items: list[NewsItem],
    *,
    feed_count: int,
    previous_filename: str | None,
) -> str:
    lines = ["# CNBeta 新闻更新", ""]
    if previous_filename:
        lines.append(f"上一批: [{previous_filename}](backup/{previous_filename})")
        lines.append("")
    lines.extend(
        [
            f"抓取时间: {format_beijing_time(beijing_now(), with_label=True)}",
            f"来源: {feed_count} 个 RSS feed | 新增: {len(items)} 条",
            "",
        ]
    )
    for index, item in enumerate(items, start=1):
        when = format_beijing_time(item.published, with_label=False) or "未知时间"
        lines.append(f"<!-- item-id: {item.item_id} -->")
        lines.extend(
            [
                f"## {index}. [{item.category_label}] {item.title}",
                "",
                f"- **链接**: {item.link}",
                f"- **时间**: {when}",
            ]
        )
        if item.summary:
            lines.append(f"- **摘要**: {item.summary}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_update_markdown(
    items: list[NewsItem],
    *,
    update_dir: Path,
    previous: Path | None,
    feed_count: int,
    dry_run: bool = False,
) -> tuple[Path | None, Path | None]:
    """Write a timestamped update/*.md, then move the previous file to backup/."""
    if not items:
        return None, None
    update_dir.mkdir(parents=True, exist_ok=True)
    previous_filename = previous.name if previous else None
    dest = _unique_update_dest(update_dir, update_filename_for_now())
    content = build_update_markdown(
        items,
        feed_count=feed_count,
        previous_filename=previous_filename,
    )
    if dry_run:
        print(content)
        return None, None
    dest.write_text(content, encoding="utf-8")
    archived_to: Path | None = None
    if previous is not None:
        archived_to = archive_update_to_backup(previous, update_dir=update_dir)
    return dest, archived_to


def resolve_verify_ssl() -> bool:
    value = (os.environ.get("CNBETA_RSS_VERIFY_SSL") or "auto").strip().lower()
    if value in ("0", "false", "no", "off"):
        return False
    if value in ("1", "true", "yes", "on"):
        return True
    return True


def fetch_feed(url: str, *, timeout: int = 30) -> str:
    headers = {"User-Agent": "CNBetaRSSAggregator/1.0 (+https://rss.cnbeta.com.tw)"}
    verify = resolve_verify_ssl()
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, verify=verify)
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.SSLError:
        if verify:
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            resp = requests.get(url, headers=headers, timeout=timeout, verify=False)
            resp.raise_for_status()
            print(
                "[warn] SSL verification failed for CNBeta RSS; retried with verify=False. "
                "Set CNBETA_RSS_VERIFY_SSL=false to silence this warning.",
                file=sys.stderr,
            )
            return resp.text
        raise


def _strip_html(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", text or "")
    cleaned = unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _category_from_link(link: str) -> str:
    match = re.search(r"/articles/([^/]+)/", link or "")
    return match.group(1) if match else "unknown"


def _normalize_published(value: str | None) -> str:
    if not value:
        return ""
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError):
        return value.strip()


def _item_id(link: str, guid: str | None, title: str) -> str:
    if link:
        return link
    if guid:
        return guid
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()
    return f"title:{digest}"


def parse_feed(xml_text: str, *, feed_url: str) -> list[NewsItem]:
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        raise ValueError(f"invalid RSS feed (missing channel): {feed_url}")

    items: list[NewsItem] = []
    for node in channel.findall("item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        guid = (node.findtext("guid") or "").strip()
        published = _normalize_published(node.findtext("pubDate"))
        description = _strip_html(node.findtext("description") or "")
        category = _category_from_link(link)
        if not title:
            continue
        items.append(
            NewsItem(
                item_id=_item_id(link, guid, title),
                title=title,
                link=link,
                published=published,
                category=category,
                summary=description[:160],
                feed_url=feed_url,
            )
        )
    return items


def fetch_all_feeds(feed_urls: list[str]) -> list[NewsItem]:
    merged: dict[str, NewsItem] = {}
    for url in feed_urls:
        xml_text = fetch_feed(url)
        for item in parse_feed(xml_text, feed_url=url):
            merged[item.item_id] = item
    return list(merged.values())


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"seen_ids": [], "last_run": None}
    data = json.loads(path.read_text(encoding="utf-8"))
    seen = data.get("seen_ids") or []
    if not isinstance(seen, list):
        seen = []
    return {"seen_ids": [str(x) for x in seen], "last_run": data.get("last_run")}


def save_state(path: Path, seen_ids: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "seen_ids": seen_ids[-500:],
        "last_run": beijing_now().isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def select_new_items(items: list[NewsItem], seen_ids: set[str]) -> list[NewsItem]:
    fresh = [item for item in items if item.item_id not in seen_ids]
    fresh.sort(key=lambda item: item.published or "", reverse=True)
    return fresh


def truncate(text: str, limit: int = 120) -> str:
    text = (text or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def build_text_message(items: list[NewsItem], *, feed_count: int) -> str:
    lines = [
        f"CNBeta 新闻更新 ({len(items)} 条)",
        f"抓取时间: {format_beijing_time(beijing_now(), with_label=True)}",
        f"来源: {feed_count} 个 RSS feed",
        "",
    ]
    for index, item in enumerate(items, start=1):
        when = format_beijing_time(item.published, with_label=False) or "未知时间"
        lines.append(f"{index}. [{item.category_label}] {item.title}")
        lines.append(f"   {when} | {item.link}")
        if item.summary:
            lines.append(f"   {truncate(item.summary, 100)}")
    return "\n".join(lines)


def build_interactive_card(items: list[NewsItem], *, feed_count: int) -> dict[str, Any]:
    body_lines = [
        f"**抓取时间** {format_beijing_time(beijing_now(), with_label=True)}",
        f"**来源** {feed_count} 个 RSS feed | **新增** {len(items)} 条",
        "",
    ]
    for index, item in enumerate(items, start=1):
        when = format_beijing_time(item.published, with_label=False) or "未知时间"
        body_lines.append(
            f"**{index}. [{item.category_label}]** [{item.title}]({item.link})"
        )
        body_lines.append(f"_{when}_")
        if item.summary:
            body_lines.append(truncate(item.summary, 120))
        body_lines.append("")
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "📰 CNBeta 新闻更新"},
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(body_lines).strip()}},
        ],
    }


def resolve_webhook_url() -> str:
    return (os.environ.get("FEISHU_WEBHOOK_URL") or "").strip()


def resolve_webhook_secret() -> str:
    return (os.environ.get("FEISHU_WEBHOOK_SECRET") or "").strip()


def resolve_app_credentials() -> tuple[str, str]:
    app_id = (os.environ.get("FEISHU_APP_ID") or "").strip()
    app_secret = (os.environ.get("FEISHU_APP_SECRET") or "").strip()
    if not app_id or not app_secret:
        raise RuntimeError(
            "missing FEISHU_APP_ID / FEISHU_APP_SECRET in .env.local or environment"
        )
    return app_id, app_secret


def resolve_app_receive_target() -> tuple[str, str]:
    receive_id = (
        (os.environ.get("FEISHU_RECEIVE_ID") or os.environ.get("FEISHU_CHAT_ID") or "")
        .strip()
    )
    if not receive_id:
        raise RuntimeError(
            "missing FEISHU_RECEIVE_ID or FEISHU_CHAT_ID "
            "(chat_id / open_id / user_id of target chat)"
        )
    receive_id_type = (os.environ.get("FEISHU_RECEIVE_ID_TYPE") or "chat_id").strip()
    return receive_id, receive_id_type


def resolve_auth_mode() -> str:
    forced = (os.environ.get("FEISHU_AUTH_MODE") or "").strip().lower()
    if forced in ("webhook", "app"):
        return forced

    app_id = (os.environ.get("FEISHU_APP_ID") or "").strip()
    app_secret = (os.environ.get("FEISHU_APP_SECRET") or "").strip()
    if app_id and app_secret:
        return "app"
    if resolve_webhook_url():
        return "webhook"
    raise RuntimeError(
        "no Feishu credentials configured: set FEISHU_APP_ID + FEISHU_APP_SECRET "
        "(app mode) or FEISHU_WEBHOOK_URL (webhook mode)"
    )


def send_feishu_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    webhook_url = resolve_webhook_url()
    if not webhook_url:
        raise RuntimeError("missing FEISHU_WEBHOOK_URL in environment or .env.local")

    body = dict(payload)
    secret = resolve_webhook_secret()
    if secret:
        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
        sign = hashlib.sha256(string_to_sign).digest()
        import base64

        body["timestamp"] = timestamp
        body["sign"] = base64.b64encode(sign).decode("utf-8")

    resp = requests.post(webhook_url, json=body, timeout=20)
    data = resp.json()
    if resp.status_code >= 400 or data.get("code") not in (0, None):
        raise RuntimeError(f"feishu webhook failed: HTTP {resp.status_code} {data}")
    return data


def send_feishu_app(items: list[NewsItem], *, feed_count: int, use_card: bool) -> dict[str, Any]:
    from feishu_notify import send_interactive_card, send_text as send_app_text

    resolve_app_credentials()
    receive_id, receive_id_type = resolve_app_receive_target()
    kwargs = {"receive_id": receive_id, "receive_id_type": receive_id_type}
    if use_card:
        card = build_interactive_card(items, feed_count=feed_count)
        return send_interactive_card(card, **kwargs)
    text = build_text_message(items, feed_count=feed_count)
    return send_app_text(text, **kwargs)


def send_items_to_feishu(items: list[NewsItem], *, feed_count: int, use_card: bool) -> dict[str, Any]:
    mode = resolve_auth_mode()
    if mode == "app":
        return send_feishu_app(items, feed_count=feed_count, use_card=use_card)

    if use_card:
        payload = {
            "msg_type": "interactive",
            "card": build_interactive_card(items, feed_count=feed_count),
        }
    else:
        payload = {
            "msg_type": "text",
            "content": {"text": build_text_message(items, feed_count=feed_count)},
        }
    return send_feishu_webhook(payload)


def run(
    *,
    max_items: int,
    dry_run: bool,
    fetch_only: bool,
    reset_state: bool,
    use_card: bool,
    skip_update_md: bool = False,
) -> dict[str, Any]:
    feed_urls = resolve_feed_urls()
    state_path = resolve_state_path()
    update_dir = resolve_update_dir()
    state = load_state(state_path)
    seen_ids = set() if reset_state else set(state.get("seen_ids") or [])

    previous_md = None if reset_state else find_latest_update_md(update_dir)
    md_seen_ids = (
        set()
        if reset_state or previous_md is None
        else parse_item_ids_from_update_md(previous_md)
    )

    all_items = fetch_all_feeds(feed_urls)
    new_items = select_new_items(all_items, md_seen_ids)[:max_items]

    result = {
        "feeds": feed_urls,
        "fetched_total": len(all_items),
        "new_count": len(new_items),
        "sent": False,
        "dry_run": dry_run,
        "previous_update": previous_md.name if previous_md else None,
        "update_path": None,
        "items": [asdict(item) for item in new_items],
    }

    if fetch_only:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result

    if not new_items:
        print("[info] no new CNBeta items")
        save_state(state_path, list(seen_ids))
        return result

    if dry_run:
        if skip_update_md:
            print(build_text_message(new_items, feed_count=len(feed_urls)))
        else:
            write_update_markdown(
                new_items,
                update_dir=update_dir,
                previous=previous_md,
                feed_count=len(feed_urls),
                dry_run=True,
            )
        return result

    send_items_to_feishu(new_items, feed_count=len(feed_urls), use_card=use_card)
    result["sent"] = True
    update_path: Path | None = None
    if not skip_update_md:
        update_path, _archived = write_update_markdown(
            new_items,
            update_dir=update_dir,
            previous=previous_md,
            feed_count=len(feed_urls),
        )
        result["update_path"] = update_path.name if update_path else None
    for item in new_items:
        seen_ids.add(item.item_id)
    save_state(state_path, list(seen_ids))
    if update_path:
        print(f"[ok] wrote {update_path.relative_to(SKILL_DIR)}")
    print(f"[ok] sent {len(new_items)} item(s) to Feishu")
    return result


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    load_env_local()
    parser = argparse.ArgumentParser(description="CNBeta RSS → Feishu aggregator")
    parser.add_argument(
        "--max-items",
        type=int,
        default=resolve_max_items(),
        help=f"Maximum new items to send per run (default: {DEFAULT_MAX_ITEMS})",
    )
    parser.add_argument(
        "--skip-update-md",
        action="store_true",
        help="Do not write update/*.md or archive the previous update file",
    )
    parser.add_argument(
        "--fetch-only",
        action="store_true",
        help="Fetch and parse feeds; print JSON without sending or updating state",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the Feishu message but do not send or update state",
    )
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help="Ignore previous seen IDs (still updates state after a successful send)",
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help="Send plain text instead of an interactive card",
    )
    parser.add_argument(
        "--ping-feishu",
        action="store_true",
        help="Verify Feishu credentials and send a test message",
    )
    args = parser.parse_args()

    try:
        if args.ping_feishu:
            mode = resolve_auth_mode()
            if mode == "app":
                from feishu_notify import get_tenant_access_token, send_text as send_app_text

                token = get_tenant_access_token(force=True)
                print(f"[ok] app mode: tenant_access_token acquired ({token[:12]}...)")
                try:
                    receive_id, receive_id_type = resolve_app_receive_target()
                except RuntimeError as exc:
                    print(f"[warn] {exc}", file=sys.stderr)
                    print(
                        "[info] token fetch succeeded; set FEISHU_RECEIVE_ID or "
                        "FEISHU_CHAT_ID to complete the send test",
                        file=sys.stderr,
                    )
                    return 0
                send_app_text(
                    "CNBeta RSS Feishu app bot test OK",
                    receive_id=receive_id,
                    receive_id_type=receive_id_type,
                )
                print("[ok] test message sent via app bot")
            else:
                send_feishu_webhook(
                    {
                        "msg_type": "text",
                        "content": {"text": "CNBeta RSS Feishu webhook test OK"},
                    }
                )
                print("[ok] test message sent via webhook")
            return 0

        run(
            max_items=max(1, args.max_items),
            dry_run=args.dry_run,
            fetch_only=args.fetch_only,
            reset_state=args.reset_state,
            use_card=not args.text,
            skip_update_md=args.skip_update_md,
        )
        return 0
    except Exception as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
