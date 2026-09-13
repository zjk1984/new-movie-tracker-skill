# -*- coding: utf-8 -*-
"""Parse PikPak feature codes (特征码), ed2k, and magnet links."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote

PIKPAK_SHA_TEXT_RE = re.compile(
    r"PikPak://[^|\s<>\"']+\|\d+\|[A-Fa-f0-9]{40}",
    re.IGNORECASE,
)
ED2K_TEXT_RE = re.compile(
    r"ed2k://\|[^|\s<>\"']+\|\d+\|[A-Fa-f0-9]{32}\|/?",
    re.IGNORECASE,
)


def parse_pikpak_sha(value: str) -> dict[str, Any] | None:
    """Parse PikPak://filename|size|gcid_hash feature code."""
    text = (value or "").strip()
    if not text:
        return None
    if "://" in text:
        text = text.split("://", 1)[1]
    parts = text.split("|")
    if len(parts) != 3:
        return None
    name, size, file_hash = parts[0].strip(), parts[1].strip(), parts[2].strip().upper()
    if not name or not size.isdigit() or len(file_hash) != 40:
        return None
    uri = f"PikPak://{name}|{size}|{file_hash}"
    return {
        "type": "sha",
        "name": unquote(name),
        "size": size,
        "hash": file_hash,
        "uri": uri,
    }


def parse_ed2k(value: str) -> dict[str, Any] | None:
    text = (value or "").strip()
    if not text.lower().startswith("ed2k://"):
        return None
    body = text[7:]
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|/"):
        body = body[:-2]
    elif body.endswith("|"):
        body = body[:-1]
    parts = body.split("|")
    if len(parts) < 3:
        return None
    name, size, file_hash = parts[0].strip(), parts[1].strip(), parts[2].strip().upper()
    if not name or not size.isdigit() or len(file_hash) != 32:
        return None
    return {
        "type": "url",
        "url": text,
        "name": unquote(name),
        "hash": file_hash,
        "uri": text,
    }


def parse_download_link(value: str) -> dict[str, Any] | None:
    text = (value or "").strip()
    if not text:
        return None
    lower = text.lower()
    if lower.startswith("pikpak://"):
        return parse_pikpak_sha(text)
    if lower.startswith("ed2k://"):
        return parse_ed2k(text)
    if lower.startswith("magnet:") or lower.startswith("http://") or lower.startswith("https://"):
        return {"type": "url", "url": text, "uri": text}
    return None


def extract_pikpak_shas(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for match in PIKPAK_SHA_TEXT_RE.findall(text or ""):
        parsed = parse_pikpak_sha(match)
        if not parsed:
            continue
        uri = parsed["uri"]
        if uri not in seen:
            seen.add(uri)
            out.append(uri)
    return out


def extract_ed2k_links(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for match in ED2K_TEXT_RE.findall(text or ""):
        parsed = parse_ed2k(match)
        if not parsed:
            continue
        uri = parsed["uri"]
        if uri not in seen:
            seen.add(uri)
            out.append(uri)
    return out

