# -*- coding: utf-8 -*-
"""Pick the best download link for a forum post (cnsub-first policy)."""
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
    "-uc",
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


def pick_forum_cnsub_magnet(magnets: list[str]) -> str | None:
    """Return the first forum magnet tagged as Chinese-subtitled, if any."""
    return pick_forum_magnet(magnets, prefer_cnsub=True) if magnets else None


def _javdb_hit_payload(info: dict[str, Any], magnet: str) -> dict[str, Any]:
    from javdb_client import build_query_report

    return {
        "magnet": magnet,
        "javdb": {
            "id": info.get("javdb_id"),
            "number": info.get("number"),
            "title": info.get("title"),
            "release_date": info.get("release_date"),
            "content_type": info.get("content_type"),
            "content_type_label": info.get("content_type_label"),
            "has_cnsub": info.get("has_cnsub"),
            "cnsub_magnet_count": info.get("cnsub_magnet_count", 0),
            "score": info.get("score"),
            "reviews_count": info.get("reviews_count"),
            "watched_count": info.get("watched_count"),
        },
        "javdb_query": build_query_report(info),
    }


def lookup_javdb_magnet(
    javdb_client,
    number: str,
    *,
    cnsub: bool = False,
) -> dict[str, Any] | None:
    """Fetch best JavDB magnet for *number*; optionally filter to cnsub rows."""
    info = javdb_client.lookup(
        number,
        fetch_magnets=True,
        cnsub=cnsub,
        best_only=True,
    )
    magnets = info.get("magnets") or []
    if not magnets:
        return None
    return _javdb_hit_payload(info, magnets[0])


def lookup_javdb_cnsub(javdb_client, number: str) -> dict[str, Any] | None:
    return lookup_javdb_magnet(javdb_client, number, cnsub=True)


def _apply_javdb_hit_metadata(item: dict[str, Any], javdb_hit: dict[str, Any]) -> None:
    item["javdb"] = javdb_hit.get("javdb")
    if javdb_hit.get("javdb_query"):
        item["javdb_query"] = javdb_hit["javdb_query"]
    release_date = (javdb_hit.get("javdb") or {}).get("release_date")
    if release_date:
        item["release_date"] = release_date


def _prefer_cnsub_magnet(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """When two forum payloads share a number, keep the cnsub magnet."""
    old_mag = existing.get("magnet") or ""
    new_mag = candidate.get("magnet") or ""
    if magnet_has_cnsub(new_mag) and not magnet_has_cnsub(old_mag):
        return candidate
    return existing


def _upgrade_number_downloads_with_javdb_cnsub(
    paired: list[dict[str, Any]],
    javdb_client,
) -> list[dict[str, Any]]:
    """Per-number: JavDB cnsub replaces forum non-cnsub when post has no cnsub."""
    upgraded: list[dict[str, Any]] = []
    for entry in paired:
        row = dict(entry)
        magnet = row.get("magnet") or ""
        number = row.get("av_number")
        if magnet and magnet_has_cnsub(magnet):
            upgraded.append(row)
            continue
        if not number:
            upgraded.append(row)
            continue
        try:
            javdb_hit = lookup_javdb_cnsub(javdb_client, number)
        except Exception:
            upgraded.append(row)
            continue
        if not javdb_hit:
            upgraded.append(row)
            continue
        row["magnet"] = javdb_hit["magnet"]
        row["source"] = "javdb_cnsub"
        upgraded.append(row)
    return upgraded


def select_alternative_from_post(item: dict[str, Any]) -> dict[str, Any] | None:
    """
    When the post has no magnet links, pick from collected ed2k / feature codes.
    Priority: PikPak SHA > ed2k > pipe hash entry with uri.
    """
    pikpak_shas = list(item.get("pikpak_sha") or [])
    if pikpak_shas:
        return {
            "pikpak_sha": pikpak_shas[0],
            "source": "forum_pikpak_sha",
        }

    ed2k_links = list(item.get("ed2k") or [])
    if ed2k_links:
        return {
            "ed2k": ed2k_links[0],
            "source": "forum_ed2k",
        }

    for entry in item.get("hash_entries") or []:
        uri = (entry.get("uri") or "").strip()
        if not uri:
            continue
        if entry.get("kind") == "hash_label_btih" or uri.lower().startswith("magnet:"):
            return {"magnet": uri, "source": entry.get("source", "forum_bt_feature")}
        if entry.get("kind") == "pikpak_sha" or uri.lower().startswith("pikpak://"):
            return {"pikpak_sha": uri, "source": entry.get("source", "forum_pipe_code")}
        if entry.get("kind") == "ed2k" or uri.lower().startswith("ed2k://"):
            return {"ed2k": uri, "source": entry.get("source", "forum_pipe_code")}

    return None


def select_magnet(item: dict[str, Any], javdb_client=None) -> dict[str, Any] | None:
    """
    Download selection policy (cnsub-first):
    1. Forum cnsub magnet (dn/title hints, not only post title)
    2. JavDB cnsub magnet when the post has no cnsub link
    3. Forum non-cnsub magnet
    4. JavDB non-cnsub magnet (lowest)
    """
    from javdb_client import extract_av_number

    forum_magnets = list(item.get("magnets") or [])
    number = item.get("av_number") or extract_av_number(item.get("title", ""))
    if number:
        item["av_number"] = number

    def _javdb_pick(*, cnsub: bool) -> dict[str, Any] | None:
        if not javdb_client or not number:
            return None
        try:
            return lookup_javdb_magnet(javdb_client, number, cnsub=cnsub)
        except Exception as exc:
            item["javdb_error"] = str(exc)
            return None

    if forum_magnets:
        forum_cnsub = pick_forum_cnsub_magnet(forum_magnets)
        if forum_cnsub and magnet_has_cnsub(forum_cnsub):
            return {
                "magnet": forum_cnsub,
                "source": "forum_cnsub",
                "av_number": number,
            }

        javdb_hit = _javdb_pick(cnsub=True)
        if javdb_hit:
            _apply_javdb_hit_metadata(item, javdb_hit)
            return {
                "magnet": javdb_hit["magnet"],
                "source": "javdb_cnsub",
                "av_number": number,
            }

        return {
            "magnet": forum_magnets[0],
            "source": "forum_fallback",
            "av_number": number,
        }

    # No magnet in post — use ed2k / feature codes / hash values from the post first
    alt = select_alternative_from_post(item)
    if alt:
        alt["av_number"] = number
        return alt

    javdb_hit = _javdb_pick(cnsub=True)
    if javdb_hit:
        _apply_javdb_hit_metadata(item, javdb_hit)
        return {
            "magnet": javdb_hit["magnet"],
            "source": "javdb_cnsub",
            "av_number": number,
        }

    javdb_hit = _javdb_pick(cnsub=False)
    if javdb_hit:
        _apply_javdb_hit_metadata(item, javdb_hit)
        return {
            "magnet": javdb_hit["magnet"],
            "source": "javdb_fallback",
            "av_number": number,
        }

    return None


def number_from_magnet(magnet: str) -> str | None:
    """Extract AV number from magnet dn= or URI text."""
    from javdb_client import extract_av_number

    text = unquote(magnet or "")
    dn_match = re.search(r"[?&]dn=([^&]+)", text, flags=re.IGNORECASE)
    if dn_match:
        num = extract_av_number(unquote(dn_match.group(1)))
        if num:
            return num
    return extract_av_number(text)


def build_number_downloads(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Pair forum links inside one post to distinct AV numbers when possible."""
    from javdb_client import extract_av_number

    by_number: dict[str, dict[str, Any]] = {}

    def add(num: str | None, payload: dict[str, Any]) -> None:
        if not num:
            return
        row = {"av_number": num, **payload}
        if num not in by_number:
            by_number[num] = row
            return
        by_number[num] = _prefer_cnsub_magnet(by_number[num], row)

    for magnet in item.get("magnets") or []:
        add(number_from_magnet(magnet), {
            "magnet": magnet,
            "source": "forum_magnet_dn",
        })

    for entry in item.get("hash_entries") or []:
        uri = (entry.get("uri") or "").strip()
        if not uri:
            continue
        num = (
            (entry.get("av_number") or "").strip().upper()
            or extract_av_number(entry.get("name") or "")
            or number_from_magnet(uri)
        )
        kind = entry.get("kind") or ""
        source = entry.get("source") or "forum_hash_entry"
        payload: dict[str, Any] = {"magnet": uri, "source": source}
        if entry.get("chinese_title"):
            payload["chinese_title"] = entry["chinese_title"]
        if kind == "hash_label_btih" or uri.lower().startswith("magnet:"):
            add(num, payload)
        elif uri.lower().startswith("pikpak://"):
            add(num, {"pikpak_sha": uri, "source": source})
        elif uri.lower().startswith("ed2k:"):
            add(num, {"ed2k": uri, "source": source})

    for ed2k in item.get("ed2k") or []:
        add(extract_av_number(unquote(ed2k)), {
            "ed2k": ed2k,
            "source": "forum_ed2k",
        })

    for sha in item.get("pikpak_sha") or []:
        add(extract_av_number(unquote(sha)), {
            "pikpak_sha": sha,
            "source": "forum_pikpak_sha",
        })

    return list(by_number.values())


def _apply_download_dict(item: dict[str, Any], selection: dict[str, Any]) -> bool:
    if selection.get("magnet"):
        item["selected_magnet"] = selection["magnet"]
        item["magnet_source"] = selection.get("source", "")
        item["selected_download"] = selection["magnet"]
        item["download_source"] = selection.get("source", "")
        if selection.get("av_number"):
            item["av_number"] = selection["av_number"]
        return True
    if selection.get("pikpak_sha"):
        item["selected_pikpak_sha"] = selection["pikpak_sha"]
        item["selected_download"] = selection["pikpak_sha"]
        item["download_source"] = selection.get("source", "")
        if selection.get("av_number"):
            item["av_number"] = selection["av_number"]
        return True
    if selection.get("ed2k"):
        item["selected_ed2k"] = selection["ed2k"]
        item["selected_download"] = selection["ed2k"]
        item["download_source"] = selection.get("source", "")
        if selection.get("av_number"):
            item["av_number"] = selection["av_number"]
        return True
    return False


def _distinct_av_numbers(paired: list[dict[str, Any]]) -> set[str]:
    return {
        str(d.get("av_number")).upper()
        for d in paired
        if d.get("av_number")
    }


def apply_selection(item: dict[str, Any], javdb_client=None) -> bool:
    paired = build_number_downloads(item)
    if paired:
        if javdb_client:
            paired = _upgrade_number_downloads_with_javdb_cnsub(paired, javdb_client)
        item["number_downloads"] = paired
        ok = _apply_download_dict(item, paired[0])
        if len(_distinct_av_numbers(paired)) >= 2:
            item.pop("av_number", None)
        return ok

    selection = select_magnet(item, javdb_client)
    if not selection:
        return False
    return _apply_download_dict(item, selection)


def maybe_javdb_magnet_fallback(item: dict[str, Any], javdb_client=None) -> bool:
    """Fetch JavDB magnets when the post has an AV number but no download yet."""
    if not javdb_client:
        return bool(item.get("selected_download"))
    if item.get("selected_download") or item.get("selected_magnet"):
        return True
    if item.get("skip_reason") or item.get("_pre_gate_failed"):
        return False

    from javdb_client import build_query_report, extract_av_number

    number = item.get("av_number") or extract_av_number(item.get("title", ""))
    if not number:
        return False
    item["av_number"] = number

    try:
        info = javdb_client.lookup(number, fetch_magnets=True, best_only=True)
    except Exception as exc:
        item["javdb_error"] = str(exc)
        return False

    item["javdb_query"] = build_query_report(info)
    item["javdb"] = {
        "id": info.get("javdb_id"),
        "number": info.get("number"),
        "title": info.get("title"),
        "release_date": info.get("release_date"),
        "content_type": info.get("content_type"),
        "content_type_label": info.get("content_type_label"),
        "has_cnsub": info.get("has_cnsub"),
        "cnsub_magnet_count": info.get("cnsub_magnet_count", 0),
        "score": info.get("score"),
        "reviews_count": info.get("reviews_count"),
        "watched_count": info.get("watched_count"),
    }
    if info.get("release_date") and not item.get("release_date"):
        item["release_date"] = info["release_date"]

    magnets = info.get("magnets") or []
    if not magnets:
        return False

    item["javdb_magnets"] = magnets
    item["magnets"] = list(dict.fromkeys((item.get("magnets") or []) + magnets))
    return apply_selection(item, javdb_client)
