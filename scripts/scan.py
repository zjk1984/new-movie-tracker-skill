# -*- coding: utf-8 -*-
"""
Scan sehuatang.org forum posts and match against an actor list.
Supports multiple actor input methods: json file, directory, or direct arguments.
Uses local Chrome with persistent context to reduce Cloudflare friction.
Supports multi-page, multi-forum scanning, and optional magnet link extraction.
"""
import os
import sys
import re
import json
import argparse
import unicodedata
from urllib.parse import urljoin
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

SKILL_DIR = Path(__file__).parent.parent

CJK_SIMPLIFIED_CHARS = str.maketrans({
    "亜": "亚",
    "亞": "亚",
    "愛": "爱",
    "榮": "荣",
    "栄": "荣",
    "紗": "纱",
    "櫻": "樱",
    "桜": "樱",
    "瀬": "濑",
    "澤": "泽",
    "沢": "泽",
    "鈴": "铃",
    "鳳": "凤",
    "嶋": "岛",
    "島": "岛",
    "濱": "滨",
    "邊": "边",
    "邉": "边",
    "実": "实",
    "實": "实",
    "廣": "广",
    "広": "广",
    "麗": "丽",
    "優": "优",
    "夢": "梦",
    "咲": "咲",
    "篠": "筱",
    "來": "来",
    "龍": "龙",
    "聖": "圣",
    "華": "华",
    "葉": "叶",
})


def normalize_name(name: str) -> str:
    return unicodedata.normalize("NFKC", str(name)).strip()


def expand_iteration_mark(text: str) -> str:
    chars = []
    for ch in text:
        if ch == "々" and chars:
            chars.append(chars[-1])
        else:
            chars.append(ch)
    return "".join(chars)


def generated_name_variants(name: str) -> set[str]:
    base = normalize_name(name)
    if not base:
        return set()

    variants = {base, expand_iteration_mark(base)}
    for item in list(variants):
        variants.add(item.translate(CJK_SIMPLIFIED_CHARS))
    return {v for v in variants if v}


def as_name_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)]


def add_alias_group(alias_map: dict[str, set[str]], names) -> None:
    group = []
    seen = set()
    for raw_name in as_name_list(names):
        for name in generated_name_variants(raw_name):
            if name not in seen:
                seen.add(name)
                group.append(name)

    if len(group) < 2:
        return

    for name in group:
        alias_map.setdefault(name, set()).update(other for other in group if other != name)


def merge_alias_data(alias_map: dict[str, set[str]], data) -> None:
    if not data:
        return

    if isinstance(data, dict):
        if "aliases" in data and "name" not in data and "actor" not in data:
            merge_alias_data(alias_map, data.get("aliases"))
            merge_alias_data(alias_map, data.get("actor_aliases"))
            return

        if "name" in data or "actor" in data:
            name = data.get("name") or data.get("actor")
            aliases = data.get("aliases") or data.get("names") or data.get("variants") or []
            add_alias_group(alias_map, [name] + as_name_list(aliases) if name else aliases)
            return

        for name, aliases in data.items():
            add_alias_group(alias_map, [name] + as_name_list(aliases))
        return

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                name = item.get("name") or item.get("actor")
                aliases = item.get("aliases") or item.get("names") or item.get("variants") or []
                add_alias_group(alias_map, [name] + as_name_list(aliases) if name else aliases)
            elif isinstance(item, list):
                add_alias_group(alias_map, item)


def read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_actor_data(data) -> tuple[set[str], dict[str, set[str]]]:
    actors = set()
    alias_map: dict[str, set[str]] = {}

    def add_actor_entry(item) -> None:
        if isinstance(item, str):
            name = normalize_name(item)
            if name:
                actors.add(name)
            return

        if not isinstance(item, dict):
            return

        name = item.get("name") or item.get("actor")
        aliases = item.get("aliases") or item.get("names") or item.get("variants") or []
        names = [name] + as_name_list(aliases) if name else as_name_list(aliases)
        if name:
            actors.add(normalize_name(name))
        elif names:
            actors.add(normalize_name(names[0]))
        add_alias_group(alias_map, names)

    if isinstance(data, dict):
        raw_actors = data.get("actors", [])
        if isinstance(raw_actors, dict):
            actors.update(normalize_name(name) for name in raw_actors if normalize_name(name))
            merge_alias_data(alias_map, raw_actors)
        else:
            items = as_name_list(raw_actors) if isinstance(raw_actors, str) else (raw_actors or [])
            for item in items:
                add_actor_entry(item)

        merge_alias_data(alias_map, data.get("aliases"))
        merge_alias_data(alias_map, data.get("actor_aliases"))
        return actors, alias_map

    if isinstance(data, list):
        for item in data:
            add_actor_entry(item)

    return actors, alias_map


def load_alias_map(args, inline_aliases: dict[str, set[str]] | None = None) -> dict[str, set[str]]:
    alias_map: dict[str, set[str]] = {}
    if args.aliases_file and os.path.exists(args.aliases_file):
        try:
            merge_alias_data(alias_map, read_json(args.aliases_file))
            print(f"[info] loaded aliases from {args.aliases_file}")
        except Exception as e:
            print(f"[warn] failed to load aliases file: {e}")

    if inline_aliases:
        for name, aliases in inline_aliases.items():
            add_alias_group(alias_map, [name] + list(aliases))

    return alias_map


def expand_actor_names(actors: set[str], alias_map: dict[str, set[str]]) -> set[str]:
    expanded = set()
    pending = list(actors)

    while pending:
        raw_name = pending.pop()
        related = generated_name_variants(raw_name)
        related.update(alias_map.get(normalize_name(raw_name), set()))

        for name in related:
            if name and name not in expanded:
                expanded.add(name)
                pending.append(name)

    return expanded


def get_actors_from_dir(actors_dir: str) -> set:
    actors = set()
    if not os.path.isdir(actors_dir):
        return actors
    for name in os.listdir(actors_dir):
        full = os.path.join(actors_dir, name)
        if os.path.isdir(full) and not name.startswith("."):
            actors.add(name)
    return actors


def load_actors(args) -> tuple[set[str], dict[str, set[str]]]:
    """Load actors with priority: --actors > --actors-file > --actors-dir > error"""
    actors = set()
    inline_aliases: dict[str, set[str]] = {}
    source = ""

    # 1. Direct argument list
    if args.actors:
        actors, inline_aliases = parse_actor_data({"actors": args.actors})
        source = "command-line argument"
        if args.save_actors and actors:
            save_actors_file(actors, args.actors_file)
            print(f"[info] saved {len(actors)} actors to {args.actors_file}")
        return actors, inline_aliases

    # 2. JSON file
    if args.actors_file and os.path.exists(args.actors_file):
        try:
            actors, inline_aliases = parse_actor_data(read_json(args.actors_file))
            source = f"json file ({args.actors_file})"
            if actors:
                print(f"[info] loaded {len(actors)} actors from {source}")
                return actors, inline_aliases
        except Exception as e:
            print(f"[warn] failed to load actors file: {e}")

    # 3. Directory
    if args.actors_dir and os.path.isdir(args.actors_dir):
        actors = get_actors_from_dir(args.actors_dir)
        source = f"directory ({args.actors_dir})"
        if actors:
            print(f"[info] loaded {len(actors)} actors from {source}")
            if args.save_actors:
                save_actors_file(actors, args.actors_file)
                print(f"[info] saved {len(actors)} actors to {args.actors_file}")
            return actors, inline_aliases

    print("[err] no actor list found. provide one via --actors, --actors-file, or --actors-dir")
    print("[hint] example: --actors 佐々木さき 楪カレン 五日市芽依")
    sys.exit(1)


def save_actors_file(actors: set, path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "actors": sorted(list(actors)),
            "updated": datetime.now().isoformat(),
        }, f, ensure_ascii=False, indent=2)


def build_match_index(actors: set[str], alias_map: dict[str, set[str]]) -> dict[str, set[str]]:
    match_index: dict[str, set[str]] = {}
    for actor in actors:
        for name in expand_actor_names({actor}, alias_map):
            match_index.setdefault(name, set()).add(actor)
    return match_index


def parse_date(text: str, today: datetime) -> datetime | None:
    text = text.strip()
    if not text:
        return None
    if text.startswith("今天") or text == "刚刚":
        return today
    if text.startswith("昨天"):
        return today - timedelta(days=1)
    if text.startswith("前天"):
        return today - timedelta(days=2)

    m = re.match(r"(\d+)\s*分钟前", text)
    if m:
        return today
    m = re.match(r"(\d+)\s*小时前", text)
    if m:
        hours = int(m.group(1))
        return today if hours < 24 else today - timedelta(days=1)
    m = re.match(r"(\d+)\s*天前", text)
    if m:
        return today - timedelta(days=int(m.group(1)))

    if re.match(r"^\d{1,2}:\d{2}$", text):
        return today

    text = text.split()[0]
    patterns = [
        (r"(\d{4})-(\d{1,2})-(\d{1,2})", lambda m: datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))),
        (r"(\d{4})/(\d{1,2})/(\d{1,2})", lambda m: datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))),
        (r"(\d{1,2})-(\d{1,2})", lambda m: datetime(today.year, int(m.group(1)), int(m.group(2)))),
        (r"(\d{1,2})/(\d{1,2})", lambda m: datetime(today.year, int(m.group(1)), int(m.group(2)))),
    ]
    for pat, builder in patterns:
        m = re.match(pat, text)
        if m:
            try:
                return builder(m)
            except ValueError:
                continue
    return None


def find_chrome():
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), r"Google\Chrome\Application\chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), r"Google\Chrome\Application\chrome.exe"),
        "/usr/local/bin/google-chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def build_page_url(base_url: str, page: int) -> str:
    if page == 1:
        return base_url
    replaced = re.sub(r"(-\d+)(\.html?)$", lambda m: f"-{page}{m.group(2)}", base_url)
    if replaced == base_url:
        if "?" in base_url:
            replaced = re.sub(r"[?&]page=\d+", "", base_url)
            replaced += f"&page={page}"
        else:
            replaced = f"{base_url}?page={page}"
    return replaced


def parse_posts_from_page(page):
    posts = []
    try:
        page.wait_for_selector("table#threadlisttableid, #threadlist, tbody[id^='normalthread']", timeout=10000)
    except PlaywrightTimeout:
        pass

    rows = page.locator("tbody[id^='normalthread']")
    row_count = rows.count()
    if row_count > 0:
        for i in range(row_count):
            row = rows.nth(i)
            try:
                title_el = row.locator("a.s.xst, a.xst, th a[href*='thread']").first
                title = title_el.inner_text(timeout=2000).strip() if title_el.count() > 0 else ""
                href = title_el.get_attribute("href") if title_el.count() > 0 else ""
                cat_el = row.locator("th em a").first
                category = cat_el.inner_text(timeout=1000).strip() if cat_el.count() > 0 else ""
                if category:
                    title = f"[{category}] {title}"
                date_el = row.locator("td.by em, td.by span, .by em, .by span").first
                date_text = date_el.inner_text(timeout=2000).strip() if date_el.count() > 0 else ""
                if title:
                    posts.append({"title": title, "date_text": date_text, "href": str(href)})
            except Exception:
                continue
    else:
        links = page.locator("a[href*='thread']")
        n = links.count()
        seen = set()
        for i in range(min(n, 200)):
            try:
                el = links.nth(i)
                title = el.inner_text(timeout=1000).strip()
                href = el.get_attribute("href") or ""
                if title and title not in seen and len(title) > 4:
                    seen.add(title)
                    date_text = ""
                    try:
                        parent = el.locator("xpath=../../..")
                        if parent.count() > 0:
                            de = parent.locator("em, span.date, .by em").first
                            date_text = de.inner_text(timeout=1000).strip() if de.count() > 0 else ""
                    except Exception:
                        pass
                    posts.append({"title": title, "date_text": date_text, "href": str(href)})
            except Exception:
                continue
    return posts


def pass_age_gate(page) -> bool:
    """Click through the 18+ age verification landing page if present."""
    try:
        content = page.content()
    except Exception:
        return False
    if "满18岁" not in content and "If you are over 18" not in content:
        return False
    print("[info] age gate detected, clicking through...")
    for selector in [
        'text="满18岁，请点此进入"',
        'text="If you are over 18, please click here"',
        'a:has-text("满18岁")',
        'a:has-text("over 18")',
    ]:
        try:
            el = page.locator(selector).first
            if el.count() > 0:
                el.click(timeout=5000)
                page.wait_for_load_state("domcontentloaded", timeout=15000)
                page.wait_for_timeout(2000)
                print("[info] age gate passed")
                return True
        except Exception:
            continue
    return False


def parse_date_arg(value: str) -> datetime:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y/%m"):
        try:
            dt = datetime.strptime(value, fmt)
            if fmt in ("%Y-%m", "%Y/%m"):
                return dt.replace(day=1)
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)
        except ValueError:
            continue
    raise ValueError(f"invalid date: {value}")


def month_end(dt: datetime) -> datetime:
    if dt.month == 12:
        nxt = dt.replace(year=dt.year + 1, month=1, day=1)
    else:
        nxt = dt.replace(month=dt.month + 1, day=1)
    return nxt - timedelta(days=1)


def post_in_range(
    dt: datetime | None,
    since: datetime | None,
    until: datetime | None,
    cutoff: datetime,
    *,
    keyword_only: bool = False,
) -> bool:
    if keyword_only and not since and not until:
        return True
    if since or until:
        if not dt:
            return False
        if since and dt < since:
            return False
        if until and dt > until:
            return False
        return True
    return bool(dt and dt >= cutoff)


def extract_thread_links(page, href: str, forum_url: str) -> dict[str, list]:
    if not href:
        return {"magnets": [], "ed2k": [], "pikpak_sha": [], "hash_entries": []}
    full_url = urljoin(forum_url, href)
    magnets: set[str] = set()
    ed2k: set[str] = set()
    pikpak_sha: set[str] = set()
    hash_entries: list[dict] = []
    try:
        page.goto(full_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        pass_age_gate(page)

        magnet_anchors = page.locator('a[href^="magnet:"]')
        for i in range(magnet_anchors.count()):
            try:
                href_val = magnet_anchors.nth(i).get_attribute("href")
                if href_val:
                    magnets.add(href_val)
            except Exception:
                continue

        ed2k_anchors = page.locator('a[href^="ed2k://"]')
        for i in range(ed2k_anchors.count()):
            try:
                href_val = ed2k_anchors.nth(i).get_attribute("href")
                if href_val:
                    ed2k.add(href_val)
            except Exception:
                continue

        text = page.content()
        for m in re.findall(r'magnet:\?xt=urn:btih:[a-fA-F0-9]+(?:&[^"\s<>]+)?', text):
            magnets.add(m)

        from pikpak_links import collect_alternatives_from_text

        alts = collect_alternatives_from_text(text)
        ed2k.update(alts["ed2k"])
        pikpak_sha.update(alts["pikpak_sha"])
        hash_entries = alts["hash_entries"]

    except Exception as e:
        print(f"[warn] failed to extract links from {full_url}: {e}")
    return {
        "magnets": list(magnets),
        "ed2k": list(ed2k),
        "pikpak_sha": list(pikpak_sha),
        "hash_entries": hash_entries,
    }


def extract_magnets(page, href: str, forum_url: str) -> list[str]:
    return extract_thread_links(page, href, forum_url)["magnets"]


def build_javdb_summary(matched: list[dict]) -> dict:
    from collections import Counter

    queried = [m for m in matched if m.get("javdb_query")]
    errors = [m for m in queried if m["javdb_query"].get("query_status") == "error"]
    with_mag = [
        m for m in queried
        if m["javdb_query"].get("magnet_status") == "available"
    ]
    empty = [
        m for m in queried
        if m["javdb_query"].get("magnet_status") == "empty"
    ]
    by_type = Counter(
        m["javdb_query"].get("content_type_label") or "?"
        for m in queried
        if m["javdb_query"].get("query_status") == "ok"
    )
    return {
        "queried": len(queried),
        "errors": len(errors),
        "with_magnets": len(with_mag),
        "without_magnets": len(empty),
        "by_content_type": dict(by_type),
    }


def format_javdb_summary_text(summary: dict) -> str:
    if not summary.get("queried"):
        return ""
    lines = [
        "",
        "javdb_query_summary:",
        f"  queried: {summary['queried']}",
        f"  with_magnets: {summary['with_magnets']}",
        f"  without_magnets: {summary['without_magnets']}",
        f"  errors: {summary['errors']}",
    ]
    if summary.get("by_content_type"):
        parts = ", ".join(f"{k} {v}" for k, v in summary["by_content_type"].items())
        lines.append(f"  by_type: {parts}")
    return "\n".join(lines)


def enrich_with_javdb(item: dict, client, args) -> None:
    from javdb_client import build_query_report, extract_av_number

    number = extract_av_number(item.get("title", ""))
    if not number:
        return
    item["av_number"] = number
    try:
        info = client.lookup(
            number,
            fetch_magnets=True,
            cnsub=bool(getattr(args, "javdb_cnsub", False)),
            hd=bool(getattr(args, "javdb_hd", False)),
            best_only=bool(getattr(args, "javdb_best", False)),
        )
    except Exception as exc:
        item["javdb_error"] = str(exc)
        print(f"[warn] javdb lookup failed for {number}: {exc}")
        return

    item["javdb_query"] = build_query_report(info)
    item["javdb"] = {
        "id": info.get("javdb_id"),
        "number": info.get("number"),
        "title": info.get("title"),
        "release_date": info.get("release_date"),
        "content_type": info.get("content_type"),
        "content_type_label": info.get("content_type_label"),
    }
    if info.get("release_date") and not item.get("release_date"):
        item["release_date"] = info["release_date"]

    javdb_magnets = info.get("magnets") or []
    if javdb_magnets:
        item["javdb_magnets"] = javdb_magnets
        if getattr(args, "javdb_magnets", False):
            merged = list(dict.fromkeys((item.get("magnets") or []) + javdb_magnets))
            item["magnets"] = merged


def match_post(
    post: dict,
    *,
    keywords: list[str],
    match_names: set[str],
    match_index: dict[str, set[str]],
    since: datetime | None,
    until: datetime | None,
    cutoff: datetime,
    today: datetime,
    all_posts: bool = False,
) -> dict | None:
    dt = parse_date(post["date_text"], today)
    if keywords:
        if not any(kw in post["title"] for kw in keywords):
            return None
        if not post_in_range(dt, since, until, cutoff, keyword_only=True):
            return None
    elif all_posts:
        if not post_in_range(dt, since, until, cutoff):
            return None
    else:
        if not post_in_range(dt, since, until, cutoff):
            return None
        matched_names = sorted(name for name in match_names if name in post["title"])
        found = sorted({actor for name in matched_names for actor in match_index.get(name, {name})})
        if not found:
            return None
    matched_names = sorted(name for name in match_names if name in post["title"])
    found = sorted({actor for name in matched_names for actor in match_index.get(name, {name})})
    item = {
        "date": (dt or today).strftime("%Y-%m-%d"),
        "date_raw": post["date_text"],
        "title": post["title"],
        "href": post["href"],
        "actors": found,
        "matched_names": matched_names,
    }
    if keywords:
        item["keywords"] = [kw for kw in keywords if kw in post["title"]]
    return item


def scrape(args):
    all_posts = bool(getattr(args, "all_posts", False))
    if all_posts:
        actors: set[str] = set()
        inline_aliases: dict[str, set[str]] = {}
        alias_map: dict[str, set[str]] = {}
        match_index: dict[str, set[str]] = {}
        match_names: set[str] = set()
        print("[info] matching all posts in date range (no actor filter)")
    else:
        actors, inline_aliases = load_actors(args)
        alias_map = load_alias_map(args, inline_aliases)
        match_index = build_match_index(actors, alias_map)
        match_names = set(match_index.keys())
    keywords = [k for k in (getattr(args, "keywords", None) or []) if k]
    if keywords:
        print(f"[info] title keyword filter: {keywords}")
    if not all_posts:
        print(f"[info] tracking {len(actors)} actors ({len(match_names)} names including aliases)")

    javdb_client = None
    if (
        getattr(args, "javdb", False)
        or getattr(args, "javdb_magnets", False)
        or getattr(args, "cnsub_priority", False)
        or getattr(args, "javdb_query", True)
    ):
        try:
            from javdb_client import JavDBClient

            javdb_client = JavDBClient(host=getattr(args, "javdb_host", None))
            print(f"[info] javdb enabled (host={javdb_client.host})")
        except ImportError as exc:
            print(f"[err] {exc}")
            sys.exit(1)
    if getattr(args, "cnsub_priority", False):
        print("[info] cnsub-first magnet policy: forum cnsub -> javdb cnsub -> forum fallback")

    chrome = find_chrome()
    if not chrome:
        print("[err] chrome not found")
        sys.exit(1)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    user_data_dir = out_dir / "chrome_profile"
    screenshot_dir = out_dir / "screenshots"
    screenshot_dir.mkdir(exist_ok=True)

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    since = parse_date_arg(args.since) if getattr(args, "since", None) else None
    until = parse_date_arg(args.until) if getattr(args, "until", None) else None
    if since and not args.until and len(args.since.strip()) in (7, 6):
        until = month_end(since)
    cutoff = today - timedelta(days=args.days - 1)
    if since:
        print(f"[info] date range: {since.strftime('%Y-%m-%d')} ~ {(until or today).strftime('%Y-%m-%d')}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            executable_path=chrome,
            headless=args.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        try:
            all_matched = []
            total_posts = 0
            total_pages_scanned = 0
            cf_keywords = ["赫拉克利特", "亚里士多德", "希腊谚语", "佛教谚语", "cf-browser-verification", "challenge-platform"]

            keywords = [k for k in (getattr(args, "keywords", None) or []) if k]

            for forum_url in args.urls:
                print(f"\n[info] scanning forum: {forum_url}")
                seen_hrefs = set()
                last_page_num = 0

                start_page = max(1, getattr(args, "start_page", 1) or 1)
                end_page = start_page + args.max_pages - 1
                if start_page > 1:
                    print(f"[info] page range: {start_page} ~ {end_page}")

                for page_num in range(start_page, end_page + 1):
                    url = build_page_url(forum_url, page_num)
                    print(f"[info] opening page {page_num}: {url}")
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(3000)
                    pass_age_gate(page)

                    title = page.title()
                    content = page.content()
                    is_cf = any(k in content or k in title for k in cf_keywords)

                    if is_cf:
                        print("[warn] cloudflare challenge detected")
                        if not args.headless:
                            print("[hint] please complete verification in the opened chrome window (if any). waiting up to 90s...")
                            for _ in range(90):
                                page.wait_for_timeout(1000)
                                try:
                                    content = page.content()
                                    title = page.title()
                                except Exception:
                                    # Page is navigating, likely challenge passed
                                    content = ""
                                    title = ""
                                still_cf = any(k in content or k in title for k in cf_keywords)
                                if not still_cf:
                                    print("[info] challenge passed")
                                    break
                            else:
                                print("[err] timeout waiting for challenge")
                                page.screenshot(path=str(screenshot_dir / f"cf_timeout_{page_num}.png"))
                                context.close()
                                return
                        else:
                            print("[warn] cloudflare on page {0}, saving partial results".format(page_num))
                            page.screenshot(path=str(screenshot_dir / f"cf_block_{page_num}.png"))
                            break

                    posts = parse_posts_from_page(page)
                    new_posts = 0
                    page_new = []
                    for post in posts:
                        if post["href"] and post["href"] not in seen_hrefs:
                            seen_hrefs.add(post["href"])
                            page_new.append(post)
                            new_posts += 1
                        elif not post["href"] and post["title"] not in seen_hrefs:
                            seen_hrefs.add(post["title"])
                            page_new.append(post)
                            new_posts += 1

                    for post in page_new:
                        item = match_post(
                            post,
                            keywords=keywords,
                            match_names=match_names,
                            match_index=match_index,
                            since=since,
                            until=until,
                            cutoff=cutoff,
                            today=today,
                            all_posts=all_posts,
                        )
                        if not item:
                            continue
                        item["forum"] = forum_url
                        if args.fetch_magnets and post.get("href"):
                            print(f"[info] fetching links for: {post['title'][:40]}...")
                            links = extract_thread_links(page, post["href"], forum_url)
                            item["magnets"] = links["magnets"]
                            item["ed2k"] = links["ed2k"]
                            item["pikpak_sha"] = links["pikpak_sha"]
                            item["hash_entries"] = links.get("hash_entries", [])
                            from magnet_select import apply_selection

                            jd = javdb_client if getattr(args, "cnsub_priority", False) else None
                            print(f"[info] selecting download: {item['title'][:40]}...")
                            if apply_selection(item, jd):
                                src = item.get("magnet_source") or item.get("download_source", "?")
                                print(f"[info]   -> {src}")
                            elif not item.get("magnets"):
                                n_alt = (
                                    len(item.get("ed2k") or [])
                                    + len(item.get("pikpak_sha") or [])
                                    + len(item.get("hash_entries") or [])
                                )
                                print(f"[info]   -> no magnet; collected {n_alt} alternative(s)")
                            else:
                                print("[info]   -> no download selected")
                        elif javdb_client:
                            print(f"[info] javdb lookup: {item['title'][:40]}...")
                            enrich_with_javdb(item, javdb_client, args)

                        if getattr(args, "region_filter", True):
                            from content_filter import apply_region_filter, is_downloadable

                            apply_region_filter(item, region_filter=True)
                            if not is_downloadable(item):
                                print(
                                    f"[skip] {item.get('content_region')}: "
                                    f"{item['title'][:50]}"
                                )
                            elif javdb_client and getattr(args, "javdb_query", True):
                                from content_filter import is_downloadable as _is_dl
                                from javdb_client import attach_javdb_query

                                if _is_dl(item) and not item.get("javdb_query"):
                                    attach_javdb_query(item, javdb_client)
                                    q = item.get("javdb_query") or {}
                                    print(f"[info]   javdb: {q.get('summary', '')}")
                        all_matched.append(item)

                    print(f"[info] page {page_num}: {len(posts)} rows, {new_posts} new, matched total {len(all_matched)}")
                    total_posts += len(posts)
                    total_pages_scanned += 1
                    last_page_num = page_num

                    if start_page == 1 and page_num >= 2 and posts:
                        dates = [parse_date(p["date_text"], today) for p in posts]
                        valid_dates = [d for d in dates if d]
                        stop_before = since if since else cutoff
                        if valid_dates and max(valid_dates) < stop_before:
                            print(f"[info] page {page_num} newest post is before range, stopping early")
                            break

                    if page_num < end_page:
                        page.wait_for_timeout(4000 if since or start_page > 1 else 2000)

            if not all_matched:
                lines = []
                lines.append("=" * 60)
                lines.append(f"scan_time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                lines.append(f"actors: {len(actors)}")
                lines.append(f"match_names: {len(match_names)}")
                lines.append(f"posts_scanned: {total_posts}")
                lines.append(f"pages_scanned: {total_pages_scanned}")
                range_label = (
                    f"{since.strftime('%Y-%m-%d')} ~ {(until or today).strftime('%Y-%m-%d')}"
                    if since else f"{cutoff.strftime('%Y-%m-%d')} ~ {today.strftime('%Y-%m-%d')}"
                )
                lines.append(f"range: {range_label}")
                lines.append("=" * 60)
                lines.append("\nno matched posts in the recent period.")
                result_text = "\n".join(lines)
                print("\n" + result_text)
                (out_dir / "result.txt").write_text(result_text, encoding="utf-8")
                page.screenshot(path=str(screenshot_dir / "last_run.png"))
                print(f"[done] results saved to {out_dir}")
                context.close()
                return

            lines = []
            lines.append("=" * 60)
            lines.append(f"scan_time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"actors: {len(actors)}")
            lines.append(f"match_names: {len(match_names)}")
            lines.append(f"posts_scanned: {total_posts}")
            lines.append(f"pages_scanned: {total_pages_scanned}")
            lines.append(f"forums: {len(args.urls)}")
            range_label = (
                f"{since.strftime('%Y-%m-%d')} ~ {(until or today).strftime('%Y-%m-%d')}"
                if since else f"{cutoff.strftime('%Y-%m-%d')} ~ {today.strftime('%Y-%m-%d')}"
            )
            lines.append(f"range: {range_label}")
            lines.append("=" * 60)
            lines.append(f"\nmatched {len(all_matched)} posts\n")
            javdb_summary = build_javdb_summary(all_matched)
            summary_text = format_javdb_summary_text(javdb_summary)
            if summary_text:
                lines.append(summary_text.strip())
                lines.append("")

            for m in all_matched:
                lines.append(f"date: {m['date']} ({m['date_raw']})")
                lines.append(f"title: {m['title']}")
                if m.get("keywords"):
                    lines.append(f"keywords: {', '.join(m['keywords'])}")
                if m.get("actors"):
                    lines.append(f"actors: {', '.join(m['actors'])}")
                if m.get("matched_names") and sorted(m["actors"]) != sorted(m["matched_names"]):
                    lines.append(f"matched_names: {', '.join(m['matched_names'])}")
                lines.append(f"href: {m['href']}")
                if m.get("av_number"):
                    lines.append(f"av_number: {m['av_number']}")
                if m.get("release_date"):
                    lines.append(f"release_date: {m['release_date']}")
                if m.get("javdb"):
                    j = m["javdb"]
                    label = j.get("content_type_label") or ""
                    lines.append(
                        f"javdb: {j.get('number')} [{label}] | {j.get('release_date')} | "
                        f"{j.get('title', '')[:50]}"
                    )
                if m.get("javdb_query"):
                    lines.append(f"javdb_query: {m['javdb_query'].get('summary', '')}")
                if m.get("javdb_error"):
                    lines.append(f"javdb_error: {m['javdb_error']}")
                if m.get("content_region"):
                    region_line = f"content_region: {m['content_region']}"
                    if m.get("domestic_subtype"):
                        region_line += f" ({m['domestic_subtype']})"
                    lines.append(region_line)
                if m.get("skip_reason"):
                    lines.append(f"skip_reason: {m['skip_reason']}")
                if m.get("selected_magnet"):
                    lines.append(f"selected_magnet ({m.get('magnet_source', '?')}): {m['selected_magnet']}")
                if m.get("selected_pikpak_sha"):
                    lines.append(
                        f"selected_pikpak_sha ({m.get('download_source', '?')}): "
                        f"{m['selected_pikpak_sha']}"
                    )
                if m.get("selected_ed2k"):
                    lines.append(
                        f"selected_ed2k ({m.get('download_source', '?')}): {m['selected_ed2k']}"
                    )
                if "magnets" in m:
                    if m["magnets"]:
                        lines.append("magnets:")
                        for mg in m["magnets"]:
                            lines.append(f"  - {mg}")
                    else:
                        lines.append("magnets: (none found)")
                if "ed2k" in m:
                    if m["ed2k"]:
                        lines.append("ed2k:")
                        for link in m["ed2k"]:
                            lines.append(f"  - {link}")
                    else:
                        lines.append("ed2k: (none found)")
                if "pikpak_sha" in m:
                    if m["pikpak_sha"]:
                        lines.append("pikpak_sha:")
                        for link in m["pikpak_sha"]:
                            lines.append(f"  - {link}")
                    else:
                        lines.append("pikpak_sha: (none found)")
                if "hash_entries" in m and m["hash_entries"]:
                    lines.append("hash_entries:")
                    for entry in m["hash_entries"]:
                        label = entry.get("label") or entry.get("uri") or entry.get("hash", "")
                        lines.append(f"  - [{entry.get('kind', '?')}] {label}")
                if m.get("selected_download") and not m.get("selected_magnet"):
                    lines.append(
                        f"selected_download ({m.get('download_source', '?')}): "
                        f"{m['selected_download']}"
                    )
                lines.append("-" * 40)

            result_text = "\n".join(lines)
            print("\n" + result_text)

            (out_dir / "result.txt").write_text(result_text, encoding="utf-8")
            (out_dir / "last_result.json").write_text(
                json.dumps({
                    "scan_time": datetime.now().isoformat(),
                    "cutoff": cutoff.strftime("%Y-%m-%d"),
                    "today": today.strftime("%Y-%m-%d"),
                    "matched": all_matched,
                    "javdb_summary": javdb_summary,
                    "total_posts": total_posts,
                    "pages_scanned": total_pages_scanned,
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            page.screenshot(path=str(screenshot_dir / "last_run.png"))
            print(f"[done] results saved to {out_dir}")

            if getattr(args, "pikpak", False):
                result_json = out_dir / "last_result.json"
                try:
                    from pikpak_download import submit_from_result

                    from pikpak_auth import resolve_folder

                    folder = resolve_folder(getattr(args, "pikpak_folder", None))
                    ok, total = submit_from_result(
                        result_json,
                        folder=folder,
                        today_only=not getattr(args, "pikpak_new_only", False),
                        new_only=getattr(args, "pikpak_new_only", False),
                    )
                    print(f"[done] pikpak: {ok}/{total} submitted to {folder}")
                except Exception as exc:
                    print(f"[err] pikpak download failed: {exc}")

        except PlaywrightTimeout:
            print("[err] page timeout")
            page.screenshot(path=str(screenshot_dir / "timeout.png"))
        except Exception as e:
            print(f"[err] {e}")
            import traceback
            traceback.print_exc()
            try:
                page.screenshot(path=str(screenshot_dir / "error.png"))
            except Exception:
                pass
        finally:
            context.close()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    default_actors_file = str(SKILL_DIR / "actors.json")

    parser = argparse.ArgumentParser(description="Scan sehuatang forum for actor updates")
    parser.add_argument("--actors", nargs="+", default=None, help="Direct actor names (space-separated)")
    parser.add_argument("--actors-file", default=default_actors_file, help="Path to actors JSON file")
    parser.add_argument("--aliases-file", default=str(SKILL_DIR / "aliases.json"), help="Path to alias mapping JSON file")
    parser.add_argument("--actors-dir", default=r"E:\sakana", help="Local actor directory (fallback)")
    parser.add_argument("--save-actors", action="store_true", help="Save loaded actors to --actors-file")
    parser.add_argument("--urls", nargs="+", default=[
        "https://www.sehuatang.org/forum-2-1.html",
        "https://www.sehuatang.org/forum-103-1.html",
        "https://www.sehuatang.org/forum-37-1.html",
    ], help="Target forum URLs to scan")
    parser.add_argument("--days", type=int, default=3, help="How many recent days to check (ignored if --since is set)")
    parser.add_argument("--since", default=None, help="Start date YYYY-MM-DD or YYYY-MM (inclusive)")
    parser.add_argument("--until", default=None, help="End date YYYY-MM-DD (inclusive; defaults to month-end for --since YYYY-MM)")
    parser.add_argument("--start-page", type=int, default=1, help="First page number to scan (default: 1)")
    parser.add_argument("--max-pages", type=int, default=5, help="Number of pages to scan from start-page")
    parser.add_argument("--headless", action="store_true", help="Run browser headless")
    parser.add_argument("--output-dir", default=".", help="Directory for results")
    parser.add_argument("--fetch-magnets", action="store_true", help="Open matched threads and extract magnet links")
    parser.add_argument("--keyword", "--keywords", dest="keywords", nargs="+", default=None, help="Match posts whose title contains any of these keywords")
    parser.add_argument("--javdb", action="store_true", help="Enrich matched posts with JavDB metadata (release date, title)")
    parser.add_argument("--javdb-magnets", action="store_true", help="Fetch magnets from JavDB API (implies --javdb)")
    parser.add_argument("--javdb-best", action="store_true", help="Only keep the best JavDB magnet (cnsub > hd > size)")
    parser.add_argument("--javdb-cnsub", action="store_true", help="Filter JavDB magnets to those with Chinese subtitles")
    parser.add_argument("--javdb-hd", action="store_true", help="Filter JavDB magnets to HD only")
    parser.add_argument("--javdb-host", default=None, help="JavDB API host (default: https://jdforrepam.com)")
    parser.add_argument(
        "--all-posts",
        action="store_true",
        help="Match all posts in the date range (skip actor name filter)",
    )
    parser.add_argument(
        "--all-regions",
        action="store_true",
        help="Download all content types (default: 日本有码 + 无码 JAV only)",
    )
    parser.add_argument(
        "--no-javdb-query",
        action="store_true",
        help="Skip JavDB metadata/magnet report per matched item",
    )
    parser.add_argument(
        "--cnsub-priority",
        action="store_true",
        help="Cnsub-first magnets: forum cnsub -> JavDB cnsub -> forum fallback (implies --fetch-magnets)",
    )
    parser.add_argument(
        "--pikpak",
        action="store_true",
        help="After scan, submit selected magnets to PikPak (uses saved token or PIKPAK_TOKEN)",
    )
    parser.add_argument(
        "--pikpak-folder",
        default=os.environ.get("PIKPAK_FOLDER", "My Pack"),
        help="PikPak target folder name (default: My Pack)",
    )
    parser.add_argument(
        "--pikpak-new-only",
        action="store_true",
        help="With --pikpak, skip magnets already in download_state.json",
    )
    args = parser.parse_args()
    if args.javdb_magnets:
        args.javdb = True
    if args.cnsub_priority:
        args.fetch_magnets = True
    args.region_filter = not args.all_regions
    args.javdb_query = not args.no_javdb_query
    if args.region_filter:
        print("[info] download filter: JAV 有码/无码 + 国产(泄密/流出/AI增强; 排除私拍/伪番号/OnlyFans)")
    if args.javdb_query:
        print("[info] javdb query report: enabled for matched 有码/无码 items")
    scrape(args)


if __name__ == "__main__":
    main()
