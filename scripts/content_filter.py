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


def is_domestic_excluded(title: str, number: str = "") -> bool:
    text = title or ""
    if "私拍" in text:
        return True
    if ONLYFANS_RE.search(text):
        return True
    if is_pseudo_jav(text, number):
        return True
    return False


def domestic_keep_reason(title: str, number: str = "") -> str | None:
    """Return keep label: 泄密/流出/AI增强/AI短剧/熟女自拍/酒店偷拍 (excludes 私拍/伪番号/OnlyFans)."""
    text = title or ""
    num = (number or extract_av_number(text) or "").upper()
    if is_domestic_excluded(text, num):
        return None
    if "AI短剧" in text or "AI真人短剧" in text:
        return "AI短剧"
    if "熟女" in text:
        return "熟女自拍"
    if "酒店偷拍" in text:
        return "酒店偷拍"
    if "泄密" in text or "泄露" in text:
        return "泄密"
    if DOMESTIC_LEAK_OUT_RE.search(text):
        return "流出"
    if "AI增强" in text or "AI 增强" in text:
        return "AI增强"
    return None


def classify_region(item: dict[str, Any]) -> str:
    title = item.get("title") or ""
    number = (item.get("av_number") or extract_av_number(title) or "").upper()

    if WESTERN_RE.search(title):
        return "western"
    if FC2_RE.search(title) or number.startswith("FC2"):
        return "fc2"
    if HEYZO_RE.search(title) or number.startswith("HEYZO"):
        return "uncensored"

    # Domestic — must be checked before generic 无码 markers
    keep = domestic_keep_reason(title, number)
    if keep:
        return "domestic_leak"
    if is_domestic_uncensored(title):
        return "domestic_other"

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

    return "other"


def is_jav_censored(item: dict[str, Any]) -> bool:
    return classify_region(item) == "jav_censored"


def is_downloadable(item: dict[str, Any]) -> bool:
    region = item.get("content_region") or classify_region(item)
    return region in DOWNLOADABLE_REGIONS


def apply_region_filter(item: dict[str, Any], *, region_filter: bool = True) -> bool:
    """Tag item with content_region; strip magnets when not in DOWNLOADABLE_REGIONS."""
    region = classify_region(item)
    item["content_region"] = region
    number = extract_av_number(item.get("title", ""))
    if number:
        item["av_number"] = number

    if region == "domestic_leak":
        item["domestic_subtype"] = domestic_keep_reason(
            item.get("title", ""),
            item.get("av_number") or number or "",
        )

    downloadable = region in DOWNLOADABLE_REGIONS
    if not region_filter or downloadable:
        return downloadable

    item["skip_reason"] = f"excluded_{region}"
    item.pop("selected_magnet", None)
    item["magnet_source"] = f"skipped_{region}"
    item["magnets"] = []
    item["ed2k"] = []
    item["pikpak_sha"] = []
    item["hash_entries"] = []
    item.pop("selected_pikpak_sha", None)
    item.pop("selected_ed2k", None)
    item.pop("selected_download", None)
    item.pop("download_source", None)
    item.pop("domestic_subtype", None)
    item.pop("javdb_magnets", None)
    return False
