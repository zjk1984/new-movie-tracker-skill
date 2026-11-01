# -*- coding: utf-8 -*-
"""Build Jellyfin/Kodi-compatible movie NFO XML from JavDB metadata."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from javdb_client import _any_str, extract_tag_names

VIDEO_EXTENSIONS = frozenset({
    ".mp4", ".mkv", ".avi", ".wmv", ".mov", ".m4v", ".ts", ".iso", ".flv", ".webm",
})


def is_video_filename(name: str) -> bool:
    lower = (name or "").lower()
    for ext in VIDEO_EXTENSIONS:
        if lower.endswith(ext):
            return True
    return False


def video_basename_stem(name: str) -> str:
    base = (name or "").rsplit("/", 1)[-1]
    if "." in base:
        return base.rsplit(".", 1)[0]
    return base


def canonical_av_number(av_number: str) -> str:
    """Uppercase 番号 used as sidecar filename base."""
    return (av_number or "").strip().upper()


def metadata_sidecar_names(av_number: str, *, include_fanart: bool = False) -> dict[str, str]:
    """Flat sidecars directly under PikPak ``downloads`` root."""
    base = canonical_av_number(av_number)
    names = {
        "nfo": f"{base}.nfo",
        "poster": f"{base}-poster.jpg",
    }
    if include_fanart:
        names["fanart"] = f"{base}-fanart.jpg"
    return names


def _first_str(detail: dict[str, Any], *keys: str) -> str:
    for key in keys:
        val = _any_str(detail.get(key)).strip()
        if val:
            return val
    return ""


def _actress_name_from_row(row: Any) -> str:
    if not isinstance(row, dict):
        return _any_str(row).strip()
    for key in ("name_zh", "name_cn", "name_zht", "name", "username"):
        name = _any_str(row.get(key)).strip()
        if name:
            return name
    return ""


def extract_actress_names(detail: dict[str, Any]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for key in ("actresses", "actors", "actor_list", "stars"):
        raw = detail.get(key)
        if not isinstance(raw, list):
            continue
        for row in raw:
            name = _actress_name_from_row(row)
            if name and name not in seen:
                seen.add(name)
                names.append(name)
    return names


def extract_plot(detail: dict[str, Any]) -> str:
    return _first_str(detail, "description", "plot", "summary", "synopsis", "brief")


def extract_cover_url(detail: dict[str, Any]) -> str:
    direct = _first_str(
        detail,
        "cover_url",
        "large_cover_url",
        "thumb_url",
        "cover",
        "image_url",
        "poster",
    )
    if direct.startswith("http"):
        return direct
    for key in ("images", "previews", "covers"):
        raw = detail.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, str) and item.startswith("http"):
                return item
            if isinstance(item, dict):
                url = _first_str(item, "url", "large", "medium", "thumb", "cover")
                if url.startswith("http"):
                    return url
    return ""


def localize_scrape_metadata_zh(meta: dict[str, Any]) -> dict[str, Any]:
    """Translate Japanese text fields to Simplified Chinese for Jellyfin NFO."""
    from title_translate import has_japanese, translate_ja_to_zh

    out = dict(meta)
    title = _any_str(meta.get("title"))
    if title:
        out.setdefault("originaltitle", title)
        if has_japanese(title):
            zh = translate_ja_to_zh(title)
            if zh:
                out["title"] = zh

    plot = _any_str(meta.get("plot"))
    if plot and has_japanese(plot):
        from rss_translate import translate_text

        out["plot"] = translate_text(plot)

    localized_tags: list[str] = []
    for tag in meta.get("tags") or []:
        name = _any_str(tag).strip()
        if not name:
            continue
        if has_japanese(name):
            localized_tags.append(translate_ja_to_zh(name) or name)
        else:
            localized_tags.append(name)
    out["tags"] = localized_tags

    for field in ("maker_name", "series_name"):
        val = _any_str(meta.get(field))
        if val and has_japanese(val):
            zh = translate_ja_to_zh(val)
            if zh:
                out[field] = zh

    actresses: list[str] = []
    for actress in meta.get("actresses") or []:
        name = _any_str(actress).strip()
        if not name:
            continue
        if has_japanese(name):
            actresses.append(translate_ja_to_zh(name) or name)
        else:
            actresses.append(name)
    out["actresses"] = actresses
    return out


def merge_scrape_metadata(
    lookup: dict[str, Any],
    detail: dict[str, Any],
) -> dict[str, Any]:
    """Combine ``client.lookup`` result with raw ``movie_detail`` fields."""
    tags = extract_tag_names(detail) or list(lookup.get("tags") or [])
    actresses = extract_actress_names(detail)
    plot = extract_plot(detail)
    cover_url = extract_cover_url(detail)
    title = _first_str(detail, "title") or _any_str(lookup.get("title"))
    return {
        "number": _any_str(lookup.get("number") or detail.get("number")).upper(),
        "title": title,
        "originaltitle": title,
        "plot": plot,
        "release_date": _first_str(detail, "release_date") or _any_str(lookup.get("release_date")),
        "actresses": actresses,
        "tags": tags,
        "cover_url": cover_url,
        "maker_name": _first_str(detail, "maker_name") or _any_str(lookup.get("maker_name")),
        "series_name": _first_str(detail, "series_name") or _any_str(lookup.get("series_name")),
        "score": lookup.get("score"),
        "javdb_id": lookup.get("javdb_id") or detail.get("id"),
        "content_type": lookup.get("content_type"),
    }


def _xml_text(parent: ET.Element, tag: str, text: str) -> None:
    if not text:
        return
    child = ET.SubElement(parent, tag)
    child.text = text


def build_movie_nfo_xml(meta: dict[str, Any]) -> str:
    """Return UTF-8 Jellyfin/Kodi ``<movie>`` NFO document."""
    root = ET.Element("movie")

    number = _any_str(meta.get("number"))
    title = _any_str(meta.get("title"))
    if title:
        _xml_text(root, "title", title)
    if number:
        _xml_text(root, "sorttitle", number)
        _xml_text(root, "uniqueid", number)
        uid = root.find("uniqueid")
        if uid is not None:
            uid.set("type", "jav")
            uid.set("default", "true")

    original = _any_str(meta.get("originaltitle"))
    if original and original != title:
        _xml_text(root, "originaltitle", original)

    release = _any_str(meta.get("release_date"))
    if release:
        _xml_text(root, "premiered", release)
        _xml_text(root, "releasedate", release)
        year_match = re.match(r"(\d{4})", release)
        if year_match:
            _xml_text(root, "year", year_match.group(1))

    plot = _any_str(meta.get("plot"))
    if plot:
        _xml_text(root, "plot", plot)
        _xml_text(root, "outline", plot)

    maker = _any_str(meta.get("maker_name"))
    if maker:
        _xml_text(root, "studio", maker)

    series = _any_str(meta.get("series_name"))
    if series:
        _xml_text(root, "set", series)

    score = meta.get("score")
    if score is not None:
        try:
            _xml_text(root, "rating", f"{float(score):.2f}")
        except (TypeError, ValueError):
            pass

    javdb_id = _any_str(meta.get("javdb_id"))
    if javdb_id:
        uid_el = ET.SubElement(root, "uniqueid")
        uid_el.text = javdb_id
        uid_el.set("type", "javdb")
        uid_el.set("default", "false")

    for actress in meta.get("actresses") or []:
        name = _any_str(actress).strip()
        if not name:
            continue
        actor_el = ET.SubElement(root, "actor")
        _xml_text(actor_el, "name", name)
        _xml_text(actor_el, "type", "Actor")

    for tag in meta.get("tags") or []:
        tag_name = _any_str(tag).strip()
        if tag_name:
            _xml_text(root, "tag", tag_name)

    if number:
        _xml_text(root, "num", number)

    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return xml_bytes.decode("utf-8")


def validate_nfo_xml(text: str) -> None:
    """Parse NFO XML; raises on invalid structure."""
    ET.fromstring(text.encode("utf-8"))
