# -*- coding: utf-8 -*-
"""Translate Japanese title fragments to Chinese for reports."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote

SKILL_DIR = Path(__file__).resolve().parent.parent
CACHE_FILE = Path(
    os.environ.get("TITLE_TRANSLATE_CACHE", str(SKILL_DIR / "data" / "title_translate_cache.json")),
)
TRANSLATE_ENABLED = os.environ.get("TITLE_TRANSLATE", "1").strip().lower() not in {
    "0", "false", "no", "off",
}

HIRAGANA_KATAKANA_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")
AV_PREFIX_RE = re.compile(
    r"^\s*(?:\[[^\]]+\]\s*)*(?:【[^】]+】\s*)*(?:\[[^\]]+\]\s*)*"
    r"(?:[A-Z]{2,10}-\d{2,5})?\s*",
    re.IGNORECASE,
)

_cache: dict[str, str] = {}
_last_request_at = 0.0
_cache_loaded = False


def has_japanese(text: str) -> bool:
    return bool(HIRAGANA_KATAKANA_RE.search(text or ""))


def _load_disk_cache() -> None:
    global _cache_loaded
    if _cache_loaded:
        return
    _cache_loaded = True
    if not CACHE_FILE.exists():
        return
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            _cache.update({str(k): str(v) for k, v in data.items()})
    except (OSError, json.JSONDecodeError):
        pass


def _save_disk_cache() -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(
        json.dumps(_cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _rate_limit_pause(min_interval: float = 0.35) -> None:
    global _last_request_at
    now = time.time()
    wait = min_interval - (now - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.time()


def _translate_with_mymemory(text: str) -> str:
    from deep_translator import MyMemoryTranslator

    _rate_limit_pause()
    return MyMemoryTranslator(
        source="japanese",
        target="chinese simplified",
    ).translate(text[:500])


def _translate_with_google(text: str) -> str:
    from deep_translator import GoogleTranslator

    _rate_limit_pause(0.5)
    return GoogleTranslator(source="ja", target="zh-CN").translate(text[:500])


def translate_ja_to_zh(text: str) -> str:
    text = (text or "").strip()
    if not text or not has_japanese(text):
        return ""
    if not TRANSLATE_ENABLED:
        return ""
    _load_disk_cache()
    if text in _cache:
        return _cache[text]
    try:
        zh = (_translate_with_mymemory(text) or "").strip()
    except Exception:
        zh = ""
    if not zh:
        try:
            zh = (_translate_with_google(text) or "").strip()
        except Exception:
            return ""
    if zh:
        _cache[text] = zh
        _save_disk_cache()
    return zh


def _magnet_dn_text(item: dict[str, Any]) -> str:
    uri = item.get("uri") or item.get("url") or item.get("magnet") or ""
    match = re.search(r"[?&]dn=([^&]+)", uri, flags=re.IGNORECASE)
    return unquote(match.group(1)).strip() if match else ""


def _strip_leading_av_number(text: str, av_number: str) -> str:
    text = (text or "").strip()
    if not text or not av_number:
        return text
    return re.sub(
        rf"^\s*{re.escape(av_number)}\s*",
        "",
        text,
        count=1,
        flags=re.IGNORECASE,
    ).strip()


def _javdb_title_matches_item(item: dict[str, Any], q: dict[str, Any]) -> bool:
    av_number = (item.get("av_number") or "").strip().upper()
    q_number = (q.get("number") or "").strip().upper()
    if av_number and q_number and av_number != q_number:
        return False
    return bool(q.get("title"))


def source_text_for_item(item: dict[str, Any]) -> str:
    region = item.get("content_region") or ""
    q = item.get("javdb_query") or {}
    if region in {"jav_censored", "uncensored", "fc2"} and _javdb_title_matches_item(item, q):
        return str(q["title"])

    av_number = (item.get("av_number") or "").strip().upper()
    for raw in (item.get("name"), _magnet_dn_text(item), item.get("title")):
        text = _strip_leading_av_number(str(raw or ""), av_number)
        text = AV_PREFIX_RE.sub("", text.replace("\n", " ")).strip()
        if text:
            return text
    return ""


def translate_title_for_item(item: dict[str, Any]) -> str:
    text = source_text_for_item(item)
    return translate_ja_to_zh(text)
