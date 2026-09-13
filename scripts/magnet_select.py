# -*- coding: utf-8 -*-
"""Pick the best magnet for a forum post (cnsub-first policy)."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote

CNSUB_TITLE_KEYWORDS = (
    "中文字幕",
    "中字",
    "字幕",
    "中文",
    "國語",
    "国语",
    "简体",
    "繁体",
    "字幕版",
    "双语",
    "字幕组",
)

CNSUB_MAGNET_HINTS = (
    "中字",
    "中文字幕",
    "字幕",
    "cnsub",
    "chs",
    "chinese",
    "subtitle",
    "-c.",
    "-c-",
    ".c.",
    "_c.",
)


def title_has_cnsub(title: str) -> bool:
    text = title or ""
    lowered = text.lower()
    for keyword in CNSUB_TITLE_KEYWORDS:
        if keyword in text or keyword.lower() in lowered:
            return True
    return False


def magnet_has_cnsub(magnet: str) -> bool:
    text = unquote(magnet or "").lower()
    for hint in CNSUB_MAGNET_HINTS:
        if hint in text:
            return True
    if re.search(r"[-_.]c(?:\.|[-_]|$)", text):
        return True
    return False


def pick_forum_magnet(magnets: list[str], *, prefer_cnsub: bool) -> str | None:
    if not magnets:
        return None
    if prefer_cnsub:
        labeled = [m for m in magnets if magnet_has_cnsub(m)]
        if labeled:
            return labeled[0]
    return magnets[0]


def lookup_javdb_cnsub(javdb_client, number: str) -> dict[str, Any] | None:
    info = javdb_client.lookup(number, fetch_magnets=True, cnsub=True, best_only=True)
    magnets = info.get("magnets") or []
    if not magnets:
        return None
    return {
        "magnet": magnets[0],
        "javdb": {
            "id": info.get("javdb_id"),
            "number": info.get("number"),
            "title": info.get("title"),
            "release_date": info.get("release_date"),
        },
    }


def select_magnet(item: dict[str, Any], javdb_client=None) -> dict[str, Any] | None:
    """
    Cnsub-first magnet policy:
    1. Forum post marked cnsub -> forum magnet (prefer cnsub-labeled link)
    2. Else JavDB cnsub magnet
    3. Else any forum magnet
    """
    from javdb_client import extract_av_number

    title = item.get("title", "")
    forum_magnets = list(item.get("magnets") or [])
    number = item.get("av_number") or extract_av_number(title)
    if number:
        item["av_number"] = number

    if title_has_cnsub(title) and forum_magnets:
        return {
            "magnet": pick_forum_magnet(forum_magnets, prefer_cnsub=True),
            "source": "forum_cnsub",
            "av_number": number,
        }

    if javdb_client and number:
        try:
            javdb_hit = lookup_javdb_cnsub(javdb_client, number)
            if javdb_hit:
                item["javdb"] = javdb_hit.get("javdb")
                if javdb_hit["javdb"].get("release_date"):
                    item["release_date"] = javdb_hit["javdb"]["release_date"]
                return {
                    "magnet": javdb_hit["magnet"],
                    "source": "javdb_cnsub",
                    "av_number": number,
                }
        except Exception as exc:
            item["javdb_error"] = str(exc)

    if forum_magnets:
        return {
            "magnet": forum_magnets[0],
            "source": "forum_fallback",
            "av_number": number,
        }

    return None


def apply_selection(item: dict[str, Any], javdb_client=None) -> bool:
    selection = select_magnet(item, javdb_client)
    if not selection or not selection.get("magnet"):
        return False
    item["selected_magnet"] = selection["magnet"]
    item["magnet_source"] = selection["source"]
    return True
