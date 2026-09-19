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
TRANSLATE_ENABLED = os.environ.get("RSS_TRANSLATE", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
CHINESE_THRESHOLD = float(os.environ.get("RSS_TRANSLATE_CHINESE_THRESHOLD", "0.35"))
BATCH_SIZE = max(1, int(os.environ.get("RSS_TRANSLATE_BATCH_SIZE", "10")))

CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")

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


def _rate_limit_pause(min_interval: float = 0.35) -> None:
    global _last_request_at
    now = time.time()
    wait = min_interval - (now - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.time()


def _openai_configured() -> bool:
    return bool((os.environ.get("OPENAI_API_KEY") or "").strip())


def _translate_batch_openai(texts: list[str]) -> list[str]:
    import requests

    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    base_url = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    model = (os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip()
    numbered = "\n".join(f"{index + 1}. {text[:800]}" for index, text in enumerate(texts))
    prompt = (
        "Translate each numbered line to Simplified Chinese. "
        "Keep proper nouns readable. Return ONLY a JSON array of strings, "
        "one translation per line, same order and count as the input.\n\n"
        f"{numbered}"
    )
    _rate_limit_pause(0.5)
    resp = requests.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    parsed = json.loads(content)
    if not isinstance(parsed, list) or len(parsed) != len(texts):
        raise ValueError("OpenAI translation returned unexpected JSON shape")
    return [str(item).strip() for item in parsed]


def _translate_batch_fallback(texts: list[str]) -> list[str]:
    from deep_translator import GoogleTranslator

    translator = GoogleTranslator(source="auto", target="zh-CN")
    results: list[str] = []
    for text in texts:
        _rate_limit_pause()
        try:
            results.append(translator.translate(text[:5000]) or "")
        except Exception:
            results.append("")
    return results


def translate_text(text: str) -> str:
    text = (text or "").strip()
    if not text or is_primarily_chinese(text):
        return text
    if not TRANSLATE_ENABLED:
        return ""
    _load_disk_cache()
    if text in _cache:
        return _cache[text]
    translated = translate_batch([text])[0]
    _cache[text] = translated
    _save_disk_cache()
    return translated


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
        if cleaned in _cache:
            results[index] = _cache[cleaned]
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
        chunk = unique_texts[start : start + BATCH_SIZE]
        try:
            if _openai_configured():
                chunk_results = _translate_batch_openai(chunk)
            else:
                chunk_results = _translate_batch_fallback(chunk)
        except Exception:
            chunk_results = [""] * len(chunk)
        for source, target in zip(chunk, chunk_results):
            translated_by_text[source] = (target or "").strip()

    for source, indices in index_map.items():
        target = translated_by_text.get(source, "")
        _cache[source] = target
        for index in indices:
            results[index] = target
    _save_disk_cache()
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

    title_jobs: list[tuple[int, str]] = []
    summary_jobs: list[tuple[int, str]] = []
    for index, (title, summary) in enumerate(zip(titles, summaries)):
        if title and not is_primarily_chinese(title):
            title_jobs.append((index, title))
        if summary and not is_primarily_chinese(summary):
            summary_jobs.append((index, summary))

    title_results = [""] * len(items)
    summary_results = [""] * len(items)
    for index, title in enumerate(titles):
        if is_primarily_chinese(title):
            title_results[index] = title
    for index, summary in enumerate(summaries):
        if is_primarily_chinese(summary):
            summary_results[index] = summary

    if title_jobs:
        translated = translate_batch([text for _, text in title_jobs])
        for (index, _source), zh in zip(title_jobs, translated):
            title_results[index] = zh or titles[index]

    if summary_jobs:
        translated = translate_batch([text for _, text in summary_jobs])
        for (index, _source), zh in zip(summary_jobs, translated):
            summary_results[index] = zh or summaries[index]

    for index, item in enumerate(items):
        object.__setattr__(item, "title_zh", title_results[index] or titles[index])
        object.__setattr__(
            item,
            "summary_zh",
            summary_results[index] or summaries[index],
        )
    return items
