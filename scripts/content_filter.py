# -*- coding: utf-8 -*-
"""Classify forum posts; default download filter keeps Japanese censored + uncensored JAV."""
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

UNCENSORED_MARKERS = ("无码", "無碼", "无码破解", "無碼破解", "uncensored", "無修正")

DOWNLOADABLE_REGIONS = frozenset({"jav_censored", "uncensored"})


def classify_region(item: dict[str, Any]) -> str:
    title = item.get("title") or ""
    number = (item.get("av_number") or extract_av_number(title) or "").upper()

    if WESTERN_RE.search(title):
        return "western"
    if FC2_RE.search(title) or (number.startswith("FC2")):
        return "fc2"
    if HEYZO_RE.search(title) or number.startswith("HEYZO"):
        return "uncensored"
    if any(m in title for m in UNCENSORED_MARKERS) or "[无码" in title:
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

    if not region_filter or region in DOWNLOADABLE_REGIONS:
        return region in DOWNLOADABLE_REGIONS

    item["skip_reason"] = f"excluded_{region}"
    item.pop("selected_magnet", None)
    item["magnet_source"] = f"skipped_{region}"
    item["magnets"] = []
    item["ed2k"] = []
    item.pop("javdb_magnets", None)
    return False
