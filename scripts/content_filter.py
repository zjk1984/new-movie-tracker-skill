# -*- coding: utf-8 -*-
"""Classify forum posts; default filter keeps JAV + selected domestic leak/private content."""
from __future__ import annotations

import re
from typing import Any

from javdb_client import extract_av_number

AMATEUR_PREFIXES = frozenset({
    "MAAN", "GANA", "SIRO", "HBLA", "HJMO", "HAWA", "GOJU", "GOHM", "USAG",
    "NTR", "SCUTE", "GANA", "LUXU", "ARA", "MYWIFE", "HMDNV", "HMD", "HND",
})

WESTERN_RE = re.compile(
    r"\b(?:Blacked|Brazzers|RealityKings|NaughtyAmerica|BangBros|Tushy|Vixen|"
    r"Deeper|Wicked|MetArt|X-Art|OnlyFans|ManyVids|Clips4Sale)\b|"
    r"Blacked\.\d{2}\.\d{2}\.\d{2}|欧美|洋马",
    re.IGNORECASE,
)

FC2_RE = re.compile(r"\bFC2[- ]?(?:PPV[- ]?)?\d+", re.IGNORECASE)
HEYZO_RE = re.compile(r"\bHEYZO[- ]?\d+", re.IGNORECASE)
AMATEUR_NUM_RE = re.compile(
    r"^(?:\d{3}[A-Z]{2,8}|200GANA|348NTR|229SCUTE)-\d+",
    re.IGNORECASE,
)
STUDIO_NUM_RE = re.compile(r"^[A-Z]{2,6}-\d{2,5}$", re.IGNORECASE)

UNCENSORED_MARKERS = ("无码破解", "無碼破解", "uncensored", "無修正", "[无码", "[無碼")
DOMESTIC_MARKERS = ("国产无码", "國產無碼", "[国产", "[國產")
DOMESTIC_LEAK_OUT_RE = re.compile(r"(?<!未)流出")
PSEUDO_JAV_PREFIXES = frozenset({
    "XJX", "JDSY", "MDSY", "MDSR", "JDSC", "CNXX", "RXAJ", "TMW", "TMG", "YCM",
})
PSEUDO_JAV_RE = re.compile(
    r"(?:" + "|".join(PSEUDO_JAV_PREFIXES) + r")-\d+",
    re.IGNORECASE,
)
ONLYFANS_RE = re.compile(
    r"OnlyFans|HongKongDoll|Hong Kong Doll|玩偶姐姐",
    re.IGNORECASE,
)
DOMESTIC_EXCLUDED_KEYWORDS = ("私拍", "厕拍", "黑人", "情色分享", "AI短剧", "AI真人短剧")
ED2K_TITLE_RE = re.compile(
    r"ed2k://|115\s*[eE]?\s*[dD]2[kK]|[eE][dD]2[kK]",
    re.IGNORECASE,
)

DOWNLOADABLE_REGIONS = frozenset({"jav_censored", "uncensored", "domestic_leak"})


def is_domestic_uncensored(title: str) -> bool:
    text = title or ""
    return any(marker in text for marker in DOMESTIC_MARKERS)


def is_pseudo_jav(title: str, number: str = "") -> bool:
    if number:
        prefix = number.split("-", 1)[0].upper()
        if prefix in PSEUDO_JAV_PREFIXES:
            return True
    return bool(PSEUDO_JAV_RE.search(title or ""))


def title_has_ai_enhanced(title: str) -> bool:
    text = title or ""
    return "AI增强" in text or "AI 增强" in text


def is_domestic_excluded(title: str, number: str = "") -> bool:
    text = title or ""
    if title_has_ai_enhanced(text):
        return True
    for kw in DOMESTIC_EXCLUDED_KEYWORDS:
        if kw not in text:
            continue
        # 115ed2k titles bypass 情色分享 only; other exclusions still apply
        if kw == "情色分享" and title_has_ed2k(text):
            continue
        return True
    if ONLYFANS_RE.search(text):
        return True
    if is_pseudo_jav(text, number):
        return True
    return False


def title_has_ed2k(title: str) -> bool:
    return bool(ED2K_TITLE_RE.search(title or ""))


def is_domestic_context(title: str) -> bool:
    """Title suggests domestic/国产 content (distinct from Japanese JAV)."""
    text = title or ""
    if is_domestic_uncensored(text):
        return True
    if any(kw in text for kw in ("熟女", "酒店偷拍", "泄密", "泄露")):
        return True
    if DOMESTIC_LEAK_OUT_RE.search(text):
        return True
    if title_has_ed2k(text):
        return True
    return False


def _domestic_keyword_subtype(title: str, number: str = "") -> str | None:
    """Domestic keep label from title keywords (not ed2k-only fallback)."""
    text = title or ""
    num = (number or extract_av_number(text) or "").upper()
    if is_domestic_excluded(text, num):
        return None
    if "熟女" in text:
        return "熟女自拍"
    if "酒店偷拍" in text:
        return "酒店偷拍"
    if "泄密" in text or "泄露" in text:
        return "泄密"
    if DOMESTIC_LEAK_OUT_RE.search(text):
        return "流出"
    return None


def domestic_keep_reason(title: str, number: str = "", *, has_ed2k: bool = False) -> str | None:
    """Return keep label for domestic posts (excludes 私拍/厕拍/黑人/情色分享/伪番号/OnlyFans)."""
    subtype = _domestic_keyword_subtype(title, number)
    if subtype:
        return subtype
    text = title or ""
    num = (number or extract_av_number(text) or "").upper()
    if is_domestic_excluded(text, num):
        return None
    if (title_has_ed2k(text) or has_ed2k) and is_domestic_context(text):
        return "ed2k"
    return None


def _classify_jav_region(title: str, number: str) -> str | None:
    """Return JAV region when title/number indicate Japanese studio content."""
    if is_domestic_uncensored(title):
        return None
    if any(m in title for m in UNCENSORED_MARKERS):
        return "uncensored"
    if "无码" in title or "無碼" in title:
        return "uncensored"
    if number:
        prefix = number.split("-", 1)[0]
        if prefix in AMATEUR_PREFIXES or AMATEUR_NUM_RE.match(number):
            return "amateur"
        if STUDIO_NUM_RE.match(number):
            return "jav_censored"
    if "[有码" in title or "[有碼" in title:
        return "jav_censored"
    return None


def resolve_domestic_subtype(item: dict[str, Any], number: str = "") -> str | None:
    title = item.get("title", "")
    num = number or item.get("av_number") or extract_av_number(title) or ""
    has_ed2k = bool(item.get("ed2k"))
    return domestic_keep_reason(title, num, has_ed2k=has_ed2k)


def classify_region(item: dict[str, Any]) -> str:
    title = item.get("title") or ""
    number = (item.get("av_number") or extract_av_number(title) or "").upper()
    has_ed2k = bool(item.get("ed2k"))

    if WESTERN_RE.search(title):
        return "western"
    if FC2_RE.search(title) or number.startswith("FC2"):
        return "fc2"
    if HEYZO_RE.search(title) or number.startswith("HEYZO"):
        return "uncensored"

    # Domestic keywords (泄密/流出/熟女/…) before JAV — 国产标签优先于番号
    keep = _domestic_keyword_subtype(title, number)
    if keep:
        return "domestic_leak"

    # ed2k 日本片 — JAV number / 有码 / 无码 markers beat body-only ed2k links
    jav_region = _classify_jav_region(title, number)
    if jav_region:
        return jav_region

    # ed2k 国产片 — body/title ed2k only when domestic context, not blanket domestic
    keep = domestic_keep_reason(title, number, has_ed2k=has_ed2k)
    if keep:
        return "domestic_leak"
    if is_domestic_excluded(title, number) or is_domestic_uncensored(title):
        return "domestic_other"

    return "other"


def is_jav_censored(item: dict[str, Any]) -> bool:
    return classify_region(item) == "jav_censored"


def is_downloadable(item: dict[str, Any]) -> bool:
    region = item.get("content_region") or classify_region(item)
    return region in DOWNLOADABLE_REGIONS


def apply_region_filter(item: dict[str, Any], *, region_filter: bool = True) -> bool:
    """Tag item with content_region; clear selected download when excluded.

    Raw forum links (magnets, ed2k, pikpak_sha, hash_entries) are preserved
    even when excluded so they remain recoverable in last_result.json.
    """
    region = classify_region(item)
    item["content_region"] = region
    number = extract_av_number(item.get("title", ""))
    if number:
        item["av_number"] = number

    if region == "domestic_leak":
        item["domestic_subtype"] = resolve_domestic_subtype(item, number)

    downloadable = region in DOWNLOADABLE_REGIONS
    if not region_filter or downloadable:
        return downloadable

    item["skip_reason"] = f"excluded_{region}"
    item.pop("selected_magnet", None)
    item.pop("selected_pikpak_sha", None)
    item.pop("selected_ed2k", None)
    item.pop("selected_download", None)
    item.pop("download_source", None)
    item["magnet_source"] = f"skipped_{region}"
    item.pop("domestic_subtype", None)
    item.pop("javdb_magnets", None)
    return False
