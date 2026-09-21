# -*- coding: utf-8 -*-
"""Translate foreign RSS titles and summaries to Chinese for Feishu / markdown output."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
CACHE_FILE = Path(
    os.environ.get(
        "RSS_TRANSLATE_CACHE",
        str(SKILL_DIR / "data" / "rss_translate_cache.json"),
    ),
)
# Match main branch title translation toggle (TITLE_TRANSLATE); RSS_TRANSLATE is legacy alias.
_translate_flag = (
    os.environ.get("RSS_TRANSLATE")
    or os.environ.get("TITLE_TRANSLATE", "1")
)
TRANSLATE_ENABLED = _translate_flag.strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
CHINESE_THRESHOLD = float(os.environ.get("RSS_TRANSLATE_CHINESE_THRESHOLD", "0.35"))
BATCH_SIZE = max(1, int(os.environ.get("RSS_TRANSLATE_BATCH_SIZE", "8")))
MIN_REQUEST_INTERVAL = float(os.environ.get("RSS_TRANSLATE_MIN_INTERVAL", "0.5"))
BATCH_COOLDOWN = float(os.environ.get("RSS_TRANSLATE_BATCH_COOLDOWN", "2.0"))
BACKOFF_DELAYS = tuple(
    float(part.strip())
    for part in os.environ.get("RSS_TRANSLATE_BACKOFF", "0,2,5,10").split(",")
    if part.strip()
) or (0.0, 2.0, 5.0, 10.0)

CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")
HIRAGANA_KATAKANA_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")

_cache: dict[str, str] = {}
_cache_loaded = False
_last_request_at = 0.0


def chinese_ratio(text: str) -> float:
    text = (text or "").strip()
    if not text:
        return 1.0
    cjk = len(CJK_RE.findall(text))
    letters = len(re.findall(r"[A-Za-z\u4e00-\u9fff]", text))
    if letters == 0:
        return 1.0 if cjk else 0.0
    return cjk / letters


def is_primarily_chinese(text: str, *, threshold: float | None = None) -> bool:
    threshold = CHINESE_THRESHOLD if threshold is None else threshold
    return chinese_ratio(text) >= threshold


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


def _rate_limit_pause(min_interval: float | None = None) -> None:
    global _last_request_at
    interval = MIN_REQUEST_INTERVAL if min_interval is None else min_interval
    now = time.time()
    wait = interval - (now - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.time()


def _source_language(text: str) -> str:
    if HIRAGANA_KATAKANA_RE.search(text or ""):
        return "japanese"
    return "english"


def _translate_with_mymemory(text: str) -> str:
    from deep_translator import MyMemoryTranslator

    _rate_limit_pause()
    return MyMemoryTranslator(
        source=_source_language(text),
        target="chinese simplified",
    ).translate(text[:5000])


def _translate_with_google(text: str) -> str:
    from deep_translator import GoogleTranslator

    _rate_limit_pause(max(MIN_REQUEST_INTERVAL, 0.5))
    return GoogleTranslator(source="auto", target="zh-CN").translate(text[:5000])


def _is_rate_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "toomanyrequests" in message or "429" in message


def _translate_with_backoff(text: str, *, provider: str) -> str:
    last_exc: Exception | None = None
    for attempt, delay in enumerate(BACKOFF_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            if provider == "mymemory":
                return _translate_with_mymemory(text)
            return _translate_with_google(text)
        except Exception as exc:
            last_exc = exc
            if not _is_rate_limit_error(exc) or attempt == len(BACKOFF_DELAYS) - 1:
                raise
    if last_exc:
        raise last_exc
    return ""


def _is_valid_zh_translation(source: str, translated: str) -> bool:
    translated = (translated or "").strip()
    if not translated:
        return False
    if translated == source:
        return False
    return is_primarily_chinese(translated)


def translate_to_zh(text: str) -> str:
    """Translate non-Chinese text to Simplified Chinese (same client stack as title_translate)."""
    text = (text or "").strip()
    if not text or is_primarily_chinese(text):
        return text if is_primarily_chinese(text) else ""
    if not TRANSLATE_ENABLED:
        return ""
    _load_disk_cache()
    cached = _cache.get(text)
    if cached:
        return cached
    try:
        zh = _translate_with_backoff(text, provider="mymemory")
    except Exception:
        try:
            zh = _translate_with_backoff(text, provider="google")
        except Exception:
            return ""
    zh = (zh or "").strip()
    if zh:
        _cache[text] = zh
        _save_disk_cache()
    return zh


def translate_text(text: str) -> str:
    text = (text or "").strip()
    if not text or is_primarily_chinese(text):
        return text
    translated = translate_to_zh(text)
    return translated or text


def translate_batch(texts: list[str]) -> list[str]:
    pending: list[tuple[int, str]] = []
    results = [""] * len(texts)
    for index, text in enumerate(texts):
        cleaned = (text or "").strip()
        if not cleaned or is_primarily_chinese(cleaned):
            results[index] = cleaned
            continue
        if not TRANSLATE_ENABLED:
            results[index] = ""
            continue
        _load_disk_cache()
        cached = _cache.get(cleaned)
        if cached:
            results[index] = cached
        else:
            pending.append((index, cleaned))

    if not pending:
        return results

    unique_texts: list[str] = []
    index_map: dict[str, list[int]] = {}
    for index, text in pending:
        index_map.setdefault(text, []).append(index)
        if text not in unique_texts:
            unique_texts.append(text)

    translated_by_text: dict[str, str] = {}
    for start in range(0, len(unique_texts), BATCH_SIZE):
        batch = unique_texts[start : start + BATCH_SIZE]
        for source in batch:
            translated_by_text[source] = translate_to_zh(source)
        next_start = start + BATCH_SIZE
        if next_start < len(unique_texts) and BATCH_COOLDOWN > 0:
            time.sleep(BATCH_COOLDOWN)

    for source, indices in index_map.items():
        target = translated_by_text.get(source, "")
        for index in indices:
            results[index] = target
    return results


def translate_news_fields(
    *,
    title: str,
    summary: str,
) -> tuple[str, str]:
    """Return (title_zh, summary_zh). Empty zh fields mean use original only."""
    title = (title or "").strip()
    summary = (summary or "").strip()
    if is_primarily_chinese(title) and (not summary or is_primarily_chinese(summary)):
        return title, summary

    to_translate: list[str] = []
    mapping: list[str] = []
    if title and not is_primarily_chinese(title):
        to_translate.append(title)
        mapping.append("title")
    if summary and not is_primarily_chinese(summary):
        to_translate.append(summary)
        mapping.append("summary")

    if not to_translate:
        return title, summary

    translated = translate_batch(to_translate)
    title_zh = title
    summary_zh = summary
    for field, value in zip(mapping, translated):
        if field == "title" and value:
            title_zh = value
        elif field == "summary" and value:
            summary_zh = value
    return title_zh, summary_zh


def apply_translations_to_items(items: list[Any]) -> list[Any]:
    """Mutate NewsItem-like objects in place with title_zh / summary_zh."""
    titles = [getattr(item, "title", "") for item in items]
    summaries = [getattr(item, "summary", "") for item in items]

    jobs: list[tuple[int, str, str]] = []
    for index, (title, summary) in enumerate(zip(titles, summaries)):
        if title and not is_primarily_chinese(title):
            jobs.append((index, "title", title))
        if summary and not is_primarily_chinese(summary):
            jobs.append((index, "summary", summary))

    title_results = [""] * len(items)
    summary_results = [""] * len(items)
    for index, title in enumerate(titles):
        if is_primarily_chinese(title):
            title_results[index] = title
    for index, summary in enumerate(summaries):
        if is_primarily_chinese(summary):
            summary_results[index] = summary

    if jobs:
        translated = translate_batch([text for _, _field, text in jobs])
        for (index, field, source), zh in zip(jobs, translated):
            if not _is_valid_zh_translation(source, zh):
                continue
            if field == "title":
                title_results[index] = zh
            else:
                summary_results[index] = zh

    for index, item in enumerate(items):
        object.__setattr__(item, "title_zh", title_results[index])
        object.__setattr__(item, "summary_zh", summary_results[index])
    return items
