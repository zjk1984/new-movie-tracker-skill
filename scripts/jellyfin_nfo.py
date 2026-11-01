# -*- coding: utf-8 -*-
"""Build Jellyfin/Kodi-compatible movie NFO XML from JavDB metadata."""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

from javdb_client import _any_str, extract_tag_names

VIDEO_EXTENSIONS = frozenset({
    ".mp4", ".mkv", ".avi", ".wmv", ".mov", ".m4v", ".ts", ".iso", ".flv", ".webm",
})

# Direct `<movie>` child tag order for ADN-148 Jellyfin template (strict alignment).
MOVIE_NFO_CHILD_TAG_ORDER: tuple[str, ...] = (
    "plot",
    "lockdata",
    "dateadded",
    "title",
    "originaltitle",
    "director",
    "year",
    "mpaa",
    "premiered",
    "releasedate",
    "runtime",
    "tagline",
    "genre",
    "studio",
    "tag",
    "metatubeid",
    "art",
    "actor",
)


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


def nfo_art_path(basename: str) -> str:
    """Sidecar art path: basename only, or ``NFO_ART_PATH_PREFIX`` + basename."""
    base = (basename or "").strip()
    if not base:
        return ""
    prefix = os.environ.get("NFO_ART_PATH_PREFIX", "").strip()
    if not prefix:
        return base
    if prefix.endswith("/"):
        return f"{prefix}{base}"
    return f"{prefix}/{base}"


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
    if direct.startswith("//"):
        return f"https:{direct}"
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


def parse_runtime_minutes(raw: Any) -> str:
    """Return runtime minutes as a decimal string for Jellyfin ``<runtime>``."""
    if raw is None:
        return ""
    if isinstance(raw, bool):
        return ""
    if isinstance(raw, (int, float)):
        minutes = int(raw)
        return str(minutes) if minutes > 0 else ""
    text = _any_str(raw).strip()
    if not text:
        return ""
    hm = re.match(r"^(\d+)\s*:\s*(\d{1,2})\s*(?::\s*(\d{1,2}))?$", text)
    if hm:
        hours = int(hm.group(1))
        mins = int(hm.group(2))
        secs = int(hm.group(3) or 0)
        total = hours * 60 + mins + (1 if secs >= 30 else 0)
        return str(total) if total > 0 else ""
    m = re.search(r"(\d+)\s*分", text)
    if m:
        return m.group(1)
    if text.isdigit():
        return text
    return ""


def _translate_list(labels: list[str], translate_fn: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for label in labels:
        text = _any_str(label).strip()
        if not text:
            continue
        zh = translate_fn(text)
        if not zh or zh in seen:
            continue
        seen.add(zh)
        out.append(zh)
    return out


def localize_scrape_metadata_zh(meta: dict[str, Any]) -> dict[str, Any]:
    """Translate scraped JavDB strings to Simplified Chinese for Jellyfin NFO."""
    from title_translate import has_japanese, translate_av_metadata_to_zh, translate_ja_to_zh

    out = dict(meta)

    title = _any_str(meta.get("title")).strip()
    if title:
        if has_japanese(title):
            out["title"] = translate_ja_to_zh(title) or translate_av_metadata_to_zh(title)
        else:
            out["title"] = translate_av_metadata_to_zh(title)

    out["plot"] = ""

    maker = _any_str(meta.get("maker_name")).strip()
    if maker:
        out["maker_name"] = translate_av_metadata_to_zh(maker)

    director = _any_str(meta.get("director")).strip()
    if director:
        out["director"] = translate_av_metadata_to_zh(director)

    genres = _translate_list(list(meta.get("genres") or []), translate_av_metadata_to_zh)
    tags = _translate_list(list(meta.get("tags") or []), translate_av_metadata_to_zh)
    if out.get("maker_name"):
        maker_zh = _any_str(out["maker_name"])
        if maker_zh and maker_zh not in tags:
            tags.insert(0, maker_zh)
    out["genres"] = genres
    out["tags"] = tags

    actresses: list[str] = []
    for actress in meta.get("actresses") or []:
        name = _any_str(actress).strip()
        if not name:
            continue
        if has_japanese(name):
            actresses.append(translate_ja_to_zh(name) or translate_av_metadata_to_zh(name))
        else:
            actresses.append(translate_av_metadata_to_zh(name))
    out["actresses"] = actresses
    out.pop("originaltitle", None)
    return out


def nfo_display_title(meta: dict[str, Any]) -> str:
    """``{番号} {中文标题} {女优中文名}`` (primary actress appended when known)."""
    number = canonical_av_number(_any_str(meta.get("number")))
    title = _any_str(meta.get("title")).strip()
    if number and title.upper().startswith(number + " "):
        title = title[len(number) :].strip()
    elif number and title.upper() == number:
        title = ""

    actresses = meta.get("actresses") or []
    lead = _any_str(actresses[0]).strip() if actresses else ""
    if lead and lead in title:
        lead = ""

    parts: list[str] = []
    if number:
        parts.append(number)
    if title:
        parts.append(title)
    if lead:
        parts.append(lead)
    return " ".join(parts)


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
    duration = detail.get("duration")
    if duration is None:
        duration = lookup.get("duration")
    return {
        "number": _any_str(lookup.get("number") or detail.get("number")).upper(),
        "title": title,
        "plot": plot,
        "release_date": _first_str(detail, "release_date") or _any_str(lookup.get("release_date")),
        "actresses": actresses,
        "tags": tags,
        "genres": list(tags),
        "cover_url": cover_url,
        "maker_name": _first_str(detail, "maker_name") or _any_str(lookup.get("maker_name")),
        "series_name": _first_str(detail, "series_name") or _any_str(lookup.get("series_name")),
        "director": _first_str(detail, "director_name", "director"),
        "duration": duration,
        "score": lookup.get("score"),
        "javdb_id": lookup.get("javdb_id") or detail.get("id"),
        "content_type": lookup.get("content_type"),
    }


def _escape_xml_text(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _indent(level: int, line: str) -> str:
    return "  " * level + line


def _serialize_movie_nfo(lines: list[str]) -> str:
    header = '<?xml version="1.0" encoding="utf-8" standalone="yes"?>'
    body = "\n".join(lines)
    return f"{header}\n{body}\n"


def movie_nfo_direct_child_tags(xml_text: str) -> list[str]:
    """Return ordered direct child tag names under ``<movie>`` (for golden tests)."""
    root = ET.fromstring(xml_text.encode("utf-8"))
    if root.tag != "movie":
        raise ValueError("expected <movie> root")
    return [child.tag for child in root]


def build_movie_nfo_xml(meta: dict[str, Any]) -> str:
    """Return UTF-8 Jellyfin ``<movie>`` NFO strictly aligned to ADN-148 template."""
    lines: list[str] = ["<movie>"]

    lines.append(_indent(1, "<plot />"))
    lines.append(_indent(1, "<lockdata>false</lockdata>"))

    dateadded = _any_str(meta.get("dateadded")).strip()
    if not dateadded:
        dateadded = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines.append(_indent(1, f"<dateadded>{_escape_xml_text(dateadded)}</dateadded>"))

    number = canonical_av_number(_any_str(meta.get("number")))
    title = nfo_display_title(meta)
    if title:
        lines.append(_indent(1, f"<title>{_escape_xml_text(title)}</title>"))
        lines.append(_indent(1, f"<originaltitle>{_escape_xml_text(title)}</originaltitle>"))

    director = _any_str(meta.get("director")).strip()
    if director:
        lines.append(_indent(1, f"<director>{_escape_xml_text(director)}</director>"))

    release = _any_str(meta.get("release_date")).strip()
    year = ""
    if release:
        year_match = re.match(r"(\d{4})", release)
        if year_match:
            year = year_match.group(1)
            lines.append(_indent(1, f"<year>{year}</year>"))

    lines.append(_indent(1, "<mpaa>JP-18+</mpaa>"))

    if release:
        lines.append(_indent(1, f"<premiered>{_escape_xml_text(release)}</premiered>"))
        lines.append(_indent(1, f"<releasedate>{_escape_xml_text(release)}</releasedate>"))

    runtime = parse_runtime_minutes(meta.get("runtime") or meta.get("duration"))
    if runtime:
        lines.append(_indent(1, f"<runtime>{runtime}</runtime>"))

    if release:
        lines.append(_indent(1, f"<tagline>配信开始日 {_escape_xml_text(release)}</tagline>"))

    for genre in meta.get("genres") or []:
        name = _any_str(genre).strip()
        if name:
            lines.append(_indent(1, f"<genre>{_escape_xml_text(name)}</genre>"))

    maker = _any_str(meta.get("maker_name")).strip()
    lines.append(_indent(1, "<studio />"))
    if maker:
        lines.append(_indent(1, f"<studio>{_escape_xml_text(maker)}</studio>"))

    for tag in meta.get("tags") or []:
        tag_name = _any_str(tag).strip()
        if tag_name:
            lines.append(_indent(1, f"<tag>{_escape_xml_text(tag_name)}</tag>"))

    if number:
        lines.append(_indent(1, f"<metatubeid>JavBus:{number}</metatubeid>"))

    sidecars = metadata_sidecar_names(number, include_fanart=True)
    poster_path = _any_str(meta.get("poster_path")).strip() or sidecars["poster"]
    fanart_path = _any_str(meta.get("fanart_path")).strip() or sidecars.get("fanart", "")
    poster_path = nfo_art_path(poster_path)
    fanart_path = nfo_art_path(fanart_path)
    if poster_path or fanart_path:
        lines.append(_indent(1, "<art>"))
        if poster_path:
            lines.append(_indent(2, f"<poster>{_escape_xml_text(poster_path)}</poster>"))
        if fanart_path:
            lines.append(_indent(2, f"<fanart>{_escape_xml_text(fanart_path)}</fanart>"))
        lines.append(_indent(1, "</art>"))

    for actress in meta.get("actresses") or []:
        name = _any_str(actress).strip()
        if not name:
            continue
        lines.append(_indent(1, "<actor>"))
        lines.append(_indent(2, f"<name>{_escape_xml_text(name)}</name>"))
        lines.append(_indent(2, "<type>Actor</type>"))
        lines.append(_indent(1, "</actor>"))

    lines.append("</movie>")
    return _serialize_movie_nfo(lines)


def validate_nfo_xml(text: str) -> None:
    """Parse NFO XML; raises on invalid structure."""
    ET.fromstring(text.encode("utf-8"))
