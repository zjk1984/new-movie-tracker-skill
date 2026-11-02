# -*- coding: utf-8 -*-
"""Pick one magnet per Save NFO row: UC > C > cnsub > plain, then largest size hint."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote

from magnet_select import magnet_has_cnsub
from pikpak_downloads_dedupe_lib import classify_filename_variant

_SIZE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*([GgMm])[Bb]",
    re.IGNORECASE,
)


def parse_size_bytes_from_text(text: str) -> int:
    """Best-effort size from magnet dn / filename (GB/MB)."""
    best = 0
    for match in _SIZE_RE.finditer(text or ""):
        val = float(match.group(1))
        unit = match.group(2).upper()
        bytes_ = int(val * (1024**3 if unit == "G" else 1024**2))
        if bytes_ > best:
            best = bytes_
    return best


def magnet_priority_tier(name_hint: str, uri: str) -> int:
    """4=UC, 3=C, 2=cnsub (no UC/C), 1=plain."""
    combined = f"{name_hint or ''} {unquote(uri or '')}"
    variant = classify_filename_variant(combined)
    if variant >= 2:
        return 4
    if variant >= 1:
        return 3
    if magnet_has_cnsub(combined):
        return 2
    return 1


def magnet_rank_key(name_hint: str, uri: str) -> tuple[int, int, str]:
    tier = magnet_priority_tier(name_hint, uri)
    combined = f"{name_hint or ''} {unquote(uri or '')}"
    size = parse_size_bytes_from_text(combined)
    return (tier, size, uri)


def pick_best_magnet_uri(
    links: list[str],
    *,
    name_hint: str = "",
) -> tuple[str, dict[str, Any]]:
    best_uri = ""
    best_key: tuple[int, int, str] = (-1, -1, "")
    for raw in links:
        uri = str(raw or "").strip()
        if not uri:
            continue
        key = magnet_rank_key(name_hint, uri)
        if key > best_key:
            best_key = key
            best_uri = uri
    tier_labels = {4: "UC", 3: "C", 2: "cnsub", 1: "plain"}
    meta: dict[str, Any] = {
        "tier": best_key[0],
        "tier_label": tier_labels.get(best_key[0], "?"),
        "size_hint_bytes": best_key[1],
    }
    return best_uri, meta
