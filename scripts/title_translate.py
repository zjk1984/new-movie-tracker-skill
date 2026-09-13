# -*- coding: utf-8 -*-
"""Translate Japanese title fragments to Chinese for reports."""
from __future__ import annotations

import re
import time
from typing import Any

HIRAGANA_KATAKANA_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")
AV_PREFIX_RE = re.compile(
    r"^\s*(?:\[[^\]]+\]\s*)*(?:【[^】]+】\s*)*(?:\[[^\]]+\]\s*)*"
    r"(?:[A-Z]{2,10}-\d{2,5})?\s*",
    re.IGNORECASE,
)

_cache: dict[str, str] = {}
_last_request_at = 0.0


def has_japanese(text: str) -> bool:
    return bool(HIRAGANA_KATAKANA_RE.search(text or ""))


def _rate_limit_pause(min_interval: float = 0.35) -> None:
    global _last_request_at
    now = time.time()
    wait = min_interval - (now - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.time()


def translate_ja_to_zh(text: str) -> str:
    text = (text or "").strip()
    if not text or not has_japanese(text):
        return ""
    if text in _cache:
        return _cache[text]
    try:
        from deep_translator import MyMemoryTranslator

        _rate_limit_pause()
        zh = MyMemoryTranslator(
            source="japanese",
            target="chinese simplified",
        ).translate(text[:500])
        _cache[text] = zh or ""
        return _cache[text]
    except Exception:
        _cache[text] = ""
        return ""


def source_text_for_item(item: dict[str, Any]) -> str:
    region = item.get("content_region") or ""
    q = item.get("javdb_query") or {}
    if region in {"jav_censored", "uncensored", "fc2"} and q.get("title"):
        return str(q["title"])
    title = (item.get("title") or "").replace("\n", " ").strip()
    stripped = AV_PREFIX_RE.sub("", title).strip()
    return stripped or title


def translate_title_for_item(item: dict[str, Any]) -> str:
    text = source_text_for_item(item)
    return translate_ja_to_zh(text)
