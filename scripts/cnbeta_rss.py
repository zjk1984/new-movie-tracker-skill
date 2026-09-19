#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multi-source RSS aggregator with Feishu push (CNBeta-compatible entrypoint)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import requests

from env_utils import beijing_now, format_beijing_time, load_env_local, parse_datetime

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SOURCES_PATH = Path(__file__).resolve().parent / "rss_sources.json"
DEFAULT_FEEDS = ("https://rss.cnbeta.com.tw",)
DEFAULT_STATE_PATH = SKILL_DIR / "data" / "cnbeta_rss_state.json"
DEFAULT_UPDATE_DIR = SKILL_DIR / "update"
DEFAULT_MAX_ITEMS = 30
DEFAULT_MAX_ITEMS_PER_CATEGORY = 5
DEFAULT_LOOKBACK_DAYS = 2
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
UPDATE_NAME_RE = re.compile(r"^(\d{8}-\d{6})(?:_\d+)?\.md$")
UPDATE_LINK_LINE_RE = re.compile(r"^\s*-\s*\*\*链接\*\*:\s*(\S+)\s*$", re.MULTILINE)
UPDATE_LINK_RE = re.compile(r"\[[^\]]*\]\((https?://[^)]+)\)")
UPDATE_ITEM_ID_RE = re.compile(r"<!--\s*item-id:\s*(.+?)\s*-->")
UPDATE_CATEGORY_RE = re.compile(r"<!--\s*category:\s*(.+?)\s*-->")
CNBETA_SECTION_LABELS = {
    "tech": "科技",
    "game": "游戏",
    "soft": "软件",
    "science": "科学",
    "movie": "影视",
    "music": "音乐",
    "misc": "趣闻",
}
DEFAULT_CATEGORY_LABELS = {
    "tech_cn": "中文科技",
    "tech_en": "英文科技",
    "politics_econ_cn": "国内政治经济",
    "politics_econ_intl": "国际政治经济",
    "finance_cn": "国内财经",
    "finance_intl": "国际财经",
    "ai": "AI",
    "insights": "热点洞察",
    "legacy": "资讯",
}


@dataclass(frozen=True)
class FeedSource:
    id: str
    name: str
    url: str
    category: str
    notes: str = ""


@dataclass(frozen=True)
class NewsItem:
    item_id: str
    title: str
    link: str
    published: str
    category: str
    summary: str
    feed_url: str
    source_category: str = "legacy"
    source_name: str = ""
    title_zh: str = ""
    summary_zh: str = ""

    @property
    def display_title(self) -> str:
        zh = (self.title_zh or "").strip()
        original = (self.title or "").strip()
        if zh and zh != original:
            return zh
        return original

    @property
    def display_summary(self) -> str:
        zh = (self.summary_zh or "").strip()
        original = (self.summary or "").strip()
        if zh and zh != original:
            return zh
        return original

    @property
    def category_label(self) -> str:
        labels = _category_labels()
        if self.source_category != "legacy":
            return labels.get(self.source_category, self.source_category)
        if self.category in CNBETA_SECTION_LABELS:
            return CNBETA_SECTION_LABELS[self.category]
        return labels.get(self.category, self.category or "资讯")

    @property
    def display_label(self) -> str:
        if self.source_name and self.source_category != "legacy":
            return f"{self.category_label} · {self.source_name}"
        return self.category_label


_category_label_cache: dict[str, str] | None = None


def _category_labels() -> dict[str, str]:
    global _category_label_cache
    if _category_label_cache is None:
        _category_label_cache = dict(DEFAULT_CATEGORY_LABELS)
        try:
            data = json.loads(resolve_sources_path().read_text(encoding="utf-8"))
            for key, meta in (data.get("categories") or {}).items():
                label = (meta or {}).get("label")
                if label:
                    _category_label_cache[key] = label
        except (OSError, json.JSONDecodeError):
            pass
    return _category_label_cache


def _env(name: str, legacy: str | None = None, default: str = "") -> str:
    value = (os.environ.get(name) or "").strip()
    if value:
        return value
    if legacy:
        return (os.environ.get(legacy) or "").strip()
    return default


def resolve_sources_path() -> Path:
    custom = _env("RSS_SOURCES_PATH", "CNBETA_RSS_SOURCES_PATH")
    return Path(custom) if custom else DEFAULT_SOURCES_PATH


def resolve_feed_urls() -> list[str]:
    raw = _env("RSS_FEEDS", "CNBETA_RSS_FEEDS")
    if raw:
        return [part.strip() for part in raw.split(",") if part.strip()]
    return list(DEFAULT_FEEDS)


def resolve_state_path() -> Path:
    custom = _env("RSS_STATE_PATH", "CNBETA_RSS_STATE_PATH")
    return Path(custom) if custom else DEFAULT_STATE_PATH


def resolve_update_dir() -> Path:
    custom = _env("RSS_UPDATE_DIR", "CNBETA_RSS_UPDATE_DIR")
    return Path(custom) if custom else DEFAULT_UPDATE_DIR


def resolve_max_items() -> int:
    raw = _env("RSS_MAX_ITEMS", "CNBETA_RSS_MAX_ITEMS", str(DEFAULT_MAX_ITEMS))
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_ITEMS


def resolve_max_items_per_category() -> int:
    raw = _env(
        "RSS_MAX_ITEMS_PER_CATEGORY",
        "CNBETA_RSS_MAX_ITEMS_PER_CATEGORY",
        str(DEFAULT_MAX_ITEMS_PER_CATEGORY),
    )
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_ITEMS_PER_CATEGORY


def resolve_lookback_days() -> int:
    raw = _env("RSS_LOOKBACK_DAYS", "CNBETA_RSS_LOOKBACK_DAYS", str(DEFAULT_LOOKBACK_DAYS))
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_LOOKBACK_DAYS


def resolve_enabled_categories() -> set[str] | None:
    raw = _env("RSS_ENABLED_CATEGORIES", "CNBETA_RSS_ENABLED_CATEGORIES")
    if not raw:
        return None
    if raw.lower() in ("all", "*"):
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}


def load_feed_sources() -> list[FeedSource]:
    """Load curated feeds from rss_sources.json, filtered by enabled categories."""
    enabled = resolve_enabled_categories()
    path = resolve_sources_path()
    if not path.exists():
        return [
            FeedSource(
                id="cnbeta",
                name="CNBeta",
                url=url,
                category="tech_cn",
            )
            for url in resolve_feed_urls()
        ]

    data = json.loads(path.read_text(encoding="utf-8"))
    feeds: list[FeedSource] = []
    for entry in data.get("feeds") or []:
        category = str(entry.get("category") or "legacy").strip()
        if enabled is not None and category not in enabled:
            continue
        url = str(entry.get("url") or "").strip()
        if not url:
            continue
        feeds.append(
            FeedSource(
                id=str(entry.get("id") or url),
                name=str(entry.get("name") or entry.get("id") or url),
                url=url,
                category=category,
                notes=str(entry.get("notes") or ""),
            )
        )
    return feeds


def resolve_active_sources() -> list[FeedSource]:
    """Legacy RSS_FEEDS env overrides the JSON catalog."""
    legacy_urls = _env("RSS_FEEDS", "CNBETA_RSS_FEEDS")
    if legacy_urls:
        return [
            FeedSource(
                id=f"legacy-{index}",
                name="Legacy feed",
                url=url.strip(),
                category="legacy",
            )
            for index, url in enumerate(legacy_urls.split(","), start=1)
            if url.strip()
        ]
    return load_feed_sources()


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


def find_latest_dedup_md(update_dir: Path) -> Path | None:
    latest = find_latest_update_md(update_dir)
    if latest is not None:
        return latest
    backup_dir = update_dir / "backup"
    files = list_update_md_files(backup_dir)
    return files[0] if files else None


def load_seen_ids(
    *,
    update_dir: Path,
    state_path: Path,
    reset_state: bool,
) -> tuple[set[str], Path | None, Path | None]:
    if reset_state:
        return set(), None, None

    state = load_state(state_path)
    seen_ids = set(state.get("seen_ids") or [])
    dedup_md = find_latest_dedup_md(update_dir)
    if dedup_md is not None:
        seen_ids.update(parse_item_ids_from_update_md(dedup_md))
    previous_md = find_latest_update_md(update_dir)
    return seen_ids, previous_md, dedup_md


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


def group_items_by_category(items: list[NewsItem]) -> list[tuple[str, list[NewsItem]]]:
    order: list[str] = []
    buckets: dict[str, list[NewsItem]] = {}
    for item in items:
        key = item.source_category or "legacy"
        if key not in buckets:
            order.append(key)
            buckets[key] = []
        buckets[key].append(item)
    labels = _category_labels()
    return [(labels.get(key, key), buckets[key]) for key in order]


def build_update_markdown(
    items: list[NewsItem],
    *,
    feed_count: int,
    previous_filename: str | None,
) -> str:
    lines = ["# RSS 新闻更新", ""]
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
    index = 1
    for category_label, group in group_items_by_category(items):
        lines.append(f"### {category_label} ({len(group)})")
        lines.append("")
        for item in group:
            when = format_beijing_time(item.published, with_label=False) or "未知时间"
            lines.append(f"<!-- item-id: {item.item_id} -->")
            lines.append(f"<!-- category: {item.source_category} -->")
            lines.extend(
                [
                    f"## {index}. [{item.display_label}] {_format_item_title(item)}",
                    "",
                    f"- **分类**: {item.source_category}",
                    f"- **链接**: {item.link}",
                    f"- **时间**: {when}",
                ]
            )
            if item.source_name:
                lines.append(f"- **来源**: {item.source_name}")
            original_title = (item.title or "").strip()
            zh_title = (item.title_zh or "").strip()
            if zh_title and original_title and zh_title != original_title:
                lines.append(f"- **原标题**: {original_title}")
            if item.display_summary:
                lines.append(f"- **摘要**: {_format_item_summary(item, limit=500)}")
            lines.append("")
            index += 1
    return "\n".join(lines).rstrip() + "\n"


def write_update_markdown(
    items: list[NewsItem],
    *,
    update_dir: Path,
    previous: Path | None,
    feed_count: int,
    dry_run: bool = False,
) -> tuple[Path | None, Path | None]:
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
    value = _env("RSS_VERIFY_SSL", "CNBETA_RSS_VERIFY_SSL", "auto").lower()
    if value in ("0", "false", "no", "off"):
        return False
    if value in ("1", "true", "yes", "on"):
        return True
    return True


def fetch_feed(url: str, *, timeout: int = 30) -> str:
    headers = {"User-Agent": "RSSAggregator/2.0 (+multi-source)"}
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
                "[warn] SSL verification failed; retried with verify=False. "
                "Set RSS_VERIFY_SSL=false to silence this warning.",
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
        pass
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        return value.strip()


def _item_id(link: str, guid: str | None, title: str) -> str:
    if link:
        return link
    if guid:
        return guid
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()
    return f"title:{digest}"


def _first_text(node: ET.Element | None, *tags: str) -> str:
    if node is None:
        return ""
    for tag in tags:
        child = node.find(tag)
        if child is not None and (child.text or "").strip():
            return (child.text or "").strip()
        child = node.find(f"atom:{tag.split(':')[-1]}", ATOM_NS)
        if child is not None and (child.text or "").strip():
            return (child.text or "").strip()
    return ""


def _link_from_node(node: ET.Element) -> str:
    link = _first_text(node, "link")
    if link.startswith("http"):
        return link
    for child in node.findall("link"):
        href = child.attrib.get("href")
        if href:
            return href
    for child in node.findall("atom:link", ATOM_NS):
        rel = child.attrib.get("rel", "alternate")
        href = child.attrib.get("href")
        if href and rel in ("alternate", "self", ""):
            return href
    return link


def parse_feed(
    xml_text: str,
    *,
    feed_url: str,
    source: FeedSource | None = None,
) -> list[NewsItem]:
    root = ET.fromstring(xml_text)
    source_category = source.category if source else "legacy"
    source_name = source.name if source else ""

    if root.tag.endswith("feed"):
        return _parse_atom_feed(
            root,
            feed_url=feed_url,
            source_category=source_category,
            source_name=source_name,
        )

    channel = root.find("channel")
    if channel is None:
        raise ValueError(f"invalid RSS feed (missing channel): {feed_url}")

    items: list[NewsItem] = []
    for node in channel.findall("item"):
        title = _first_text(node, "title")
        link = _link_from_node(node)
        guid = _first_text(node, "guid")
        published = _normalize_published(
            _first_text(node, "pubDate", "published", "updated")
        )
        description = _strip_html(
            _first_text(node, "description", "content:encoded", "summary")
        )
        section = _category_from_link(link)
        if not title:
            continue
        items.append(
            NewsItem(
                item_id=_item_id(link, guid, title),
                title=title,
                link=link,
                published=published,
                category=section,
                summary=description[:160],
                feed_url=feed_url,
                source_category=source_category,
                source_name=source_name,
            )
        )
    return items


def _parse_atom_feed(
    root: ET.Element,
    *,
    feed_url: str,
    source_category: str,
    source_name: str,
) -> list[NewsItem]:
    items: list[NewsItem] = []
    for node in root.findall("atom:entry", ATOM_NS):
        title = _first_text(node, "title")
        link = _link_from_node(node)
        guid = _first_text(node, "id")
        published = _normalize_published(
            _first_text(node, "published", "updated")
        )
        description = _strip_html(
            _first_text(node, "summary", "content")
        )
        if not title:
            continue
        items.append(
            NewsItem(
                item_id=_item_id(link, guid, title),
                title=title,
                link=link,
                published=published,
                category="unknown",
                summary=description[:160],
                feed_url=feed_url,
                source_category=source_category,
                source_name=source_name,
            )
        )
    return items


def fetch_all_feeds(sources: list[FeedSource]) -> list[NewsItem]:
    merged: dict[str, NewsItem] = {}
    for source in sources:
        try:
            xml_text = fetch_feed(source.url)
            for item in parse_feed(xml_text, feed_url=source.url, source=source):
                merged[item.item_id] = item
        except Exception as exc:
            print(
                f"[warn] failed to fetch {source.name} ({source.url}): {exc}",
                file=sys.stderr,
            )
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


def filter_by_lookback(
    items: list[NewsItem],
    *,
    lookback_days: int,
    now: datetime | None = None,
) -> list[NewsItem]:
    if lookback_days <= 0:
        return list(items)
    now = now or beijing_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cutoff = now.astimezone(timezone.utc) - timedelta(days=lookback_days)
    filtered: list[NewsItem] = []
    for item in items:
        published = parse_datetime(item.published)
        if published is None:
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        if published.astimezone(timezone.utc) >= cutoff:
            filtered.append(item)
    return filtered


def select_new_items(items: list[NewsItem], seen_ids: set[str]) -> list[NewsItem]:
    fresh = [item for item in items if item.item_id not in seen_ids]
    fresh.sort(key=lambda item: item.published or "", reverse=True)
    return fresh


def apply_item_limits(
    items: list[NewsItem],
    *,
    max_items: int,
    max_items_per_category: int,
) -> list[NewsItem]:
    selected: list[NewsItem] = []
    per_category: dict[str, int] = {}
    for item in items:
        if len(selected) >= max_items:
            break
        key = item.source_category or "legacy"
        count = per_category.get(key, 0)
        if count >= max_items_per_category:
            continue
        selected.append(item)
        per_category[key] = count + 1
    return selected


def truncate(text: str, limit: int = 120) -> str:
    text = (text or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _format_item_title(item: NewsItem) -> str:
    original = (item.title or "").strip()
    zh = (item.title_zh or "").strip()
    if zh and original and zh != original:
        return f"{zh}（{original}）"
    return item.display_title


def _format_item_summary(item: NewsItem, *, limit: int = 120) -> str:
    original = (item.summary or "").strip()
    zh = (item.summary_zh or "").strip()
    if zh and original and zh != original:
        return truncate(f"{zh}（原文: {original}）", limit)
    return truncate(item.display_summary, limit)


def translate_items_for_output(items: list[NewsItem]) -> list[NewsItem]:
    if not items:
        return items
    from rss_translate import apply_translations_to_items

    return apply_translations_to_items(items)


def build_text_message(items: list[NewsItem], *, feed_count: int) -> str:
    lines = [
        f"RSS 新闻更新 ({len(items)} 条)",
        f"抓取时间: {format_beijing_time(beijing_now(), with_label=True)}",
        f"来源: {feed_count} 个 RSS feed",
        "",
    ]
    index = 1
    for category_label, group in group_items_by_category(items):
        lines.append(f"【{category_label}】")
        for item in group:
            when = format_beijing_time(item.published, with_label=False) or "未知时间"
            lines.append(f"{index}. [{item.display_label}] {_format_item_title(item)}")
            lines.append(f"   {when} | {item.link}")
            if item.display_summary:
                lines.append(f"   {_format_item_summary(item, limit=100)}")
            index += 1
        lines.append("")
    return "\n".join(lines).strip()


def build_interactive_card(items: list[NewsItem], *, feed_count: int) -> dict[str, Any]:
    body_lines = [
        f"**抓取时间** {format_beijing_time(beijing_now(), with_label=True)}",
        f"**来源** {feed_count} 个 RSS feed | **新增** {len(items)} 条",
        "",
    ]
    index = 1
    for category_label, group in group_items_by_category(items):
        body_lines.append(f"**【{category_label}】** ({len(group)})")
        for item in group:
            when = format_beijing_time(item.published, with_label=False) or "未知时间"
            body_lines.append(
                f"**{index}. [{item.display_label}]** "
                f"[{_format_item_title(item)}]({item.link})"
            )
            body_lines.append(f"_{when}_")
            if item.display_summary:
                body_lines.append(_format_item_summary(item, limit=120))
            body_lines.append("")
            index += 1
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "📰 RSS 新闻更新"},
        },
        "elements": [
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": "\n".join(body_lines).strip()},
            },
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
    max_items_per_category: int,
    dry_run: bool,
    fetch_only: bool,
    reset_state: bool,
    use_card: bool,
    skip_update_md: bool = False,
) -> dict[str, Any]:
    sources = resolve_active_sources()
    state_path = resolve_state_path()
    update_dir = resolve_update_dir()
    lookback_days = resolve_lookback_days()
    seen_ids, previous_md, dedup_md = load_seen_ids(
        update_dir=update_dir,
        state_path=state_path,
        reset_state=reset_state,
    )

    all_items = fetch_all_feeds(sources)
    recent_items = filter_by_lookback(all_items, lookback_days=lookback_days)
    fresh_items = select_new_items(recent_items, seen_ids)
    new_items = apply_item_limits(
        fresh_items,
        max_items=max_items,
        max_items_per_category=max_items_per_category,
    )

    categories = sorted({item.source_category for item in new_items})
    result = {
        "feeds": [source.url for source in sources],
        "sources": [asdict(source) for source in sources],
        "enabled_categories": sorted(resolve_enabled_categories() or []),
        "fetched_total": len(all_items),
        "lookback_days": lookback_days,
        "within_window_total": len(recent_items),
        "fresh_count": len(fresh_items),
        "new_count": len(new_items),
        "categories_in_batch": categories,
        "sent": False,
        "dry_run": dry_run,
        "previous_update": previous_md.name if previous_md else None,
        "dedup_source": dedup_md.name if dedup_md else None,
        "seen_count": len(seen_ids),
        "update_path": None,
        "items": [asdict(item) for item in new_items],
    }

    if fetch_only:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result

    if not new_items:
        print("[info] no new RSS items")
        save_state(state_path, list(seen_ids))
        return result

    new_items = translate_items_for_output(new_items)
    result["items"] = [asdict(item) for item in new_items]

    if dry_run:
        if skip_update_md:
            print(build_text_message(new_items, feed_count=len(sources)))
        else:
            write_update_markdown(
                new_items,
                update_dir=update_dir,
                previous=previous_md,
                feed_count=len(sources),
                dry_run=True,
            )
        return result

    send_items_to_feishu(new_items, feed_count=len(sources), use_card=use_card)
    result["sent"] = True
    update_path: Path | None = None
    if not skip_update_md:
        update_path, _archived = write_update_markdown(
            new_items,
            update_dir=update_dir,
            previous=previous_md,
            feed_count=len(sources),
        )
        result["update_path"] = update_path.name if update_path else None
    for item in new_items:
        seen_ids.add(item.item_id)
    save_state(state_path, list(seen_ids))
    if update_path:
        try:
            shown_path = update_path.relative_to(SKILL_DIR)
        except ValueError:
            shown_path = update_path
        print(f"[ok] wrote {shown_path}")
    print(f"[ok] sent {len(new_items)} item(s) to Feishu")
    return result


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    load_env_local()
    parser = argparse.ArgumentParser(
        description="Multi-source RSS → Feishu aggregator (CNBeta-compatible)"
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=resolve_max_items(),
        help=f"Maximum new items to send per run (default: {DEFAULT_MAX_ITEMS})",
    )
    parser.add_argument(
        "--max-items-per-category",
        type=int,
        default=resolve_max_items_per_category(),
        help=(
            "Maximum new items per category per run "
            f"(default: {DEFAULT_MAX_ITEMS_PER_CATEGORY})"
        ),
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
    parser.add_argument(
        "--list-sources",
        action="store_true",
        help="Print configured RSS sources and exit",
    )
    args = parser.parse_args()

    try:
        if args.list_sources:
            sources = resolve_active_sources()
            print(json.dumps([asdict(source) for source in sources], ensure_ascii=False, indent=2))
            return 0

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
                    "RSS Feishu app bot test OK",
                    receive_id=receive_id,
                    receive_id_type=receive_id_type,
                )
                print("[ok] test message sent via app bot")
            else:
                send_feishu_webhook(
                    {
                        "msg_type": "text",
                        "content": {"text": "RSS Feishu webhook test OK"},
                    }
                )
                print("[ok] test message sent via webhook")
            return 0

        run(
            max_items=max(1, args.max_items),
            max_items_per_category=max(1, args.max_items_per_category),
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
