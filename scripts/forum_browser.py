# -*- coding: utf-8 -*-
"""Shared Playwright helpers for forum scraping."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

# Discuz: thread-{tid}-{type}-{page}.html — download links live on page 1 (OP).
THREAD_HREF_RE = re.compile(r"thread-(\d+)-(\d+)-(\d+)\.html", re.IGNORECASE)


def thread_id_from_href(href: str) -> str | None:
    """Return numeric thread id from Discuz href or viewthread URL."""
    href = (href or "").strip()
    if not href:
        return None
    match = THREAD_HREF_RE.search(href)
    if match:
        return match.group(1)
    parsed = urlparse(href)
    qs = parse_qs(parsed.query)
    tid = (qs.get("tid") or [None])[0]
    return str(tid).strip() if tid else None


def canonical_thread_href(href: str) -> str:
    """Normalize thread href to page 1 so link extraction hits the OP body."""
    href = (href or "").strip()
    if not href:
        return ""
    match = THREAD_HREF_RE.search(href)
    if match:
        tid, kind = match.group(1), match.group(2)
        return f"thread-{tid}-{kind}-1.html"
    parsed = urlparse(href)
    if "viewthread" in (parsed.path or "") or "mod=viewthread" in (parsed.query or ""):
        qs = parse_qs(parsed.query)
        tid = (qs.get("tid") or [None])[0]
        if tid:
            kind = (qs.get("extra") or ["1"])[0]
            if not re.fullmatch(r"\d+", str(kind)):
                kind = "1"
            return f"thread-{tid}-{kind}-1.html"
    return href


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
