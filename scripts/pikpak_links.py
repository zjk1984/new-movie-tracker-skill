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
# filename.ext|bytes|40hex (PikPak GCID) or 32hex (ed2k hash)
PIPE_CODE_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"([^\s|<>\"'\\]{1,200}?\.(?:mp4|mkv|avi|wmv|rmvb|rar|zip|7z))"
    r"\|(\d{5,16})\|([A-Fa-f0-9]{32}|[A-Fa-f0-9]{40})"
    r"(?![A-Fa-f0-9])",
    re.IGNORECASE,
)
HASH_LABEL_RE = re.compile(
    r"(?:哈希校验|校验码|文件校验|特征码|GCID|文件哈希|hash)"
    r"[：:\s]*([A-Fa-f0-9]{32}|[A-Fa-f0-9]{40})",
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


def build_ed2k_uri(name: str, size: str, file_hash: str) -> str:
    return f"ed2k://|{name}|{size}|{file_hash.upper()}|/"


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
        "size": size,
        "hash": file_hash,
        "uri": text,
    }


def parse_pipe_code(line: str) -> dict[str, Any] | None:
    """Parse filename|size|hash pipe feature code (no scheme prefix)."""
    text = (line or "").strip()
    if not text or text.lower().startswith(("magnet:", "ed2k:", "pikpak:", "http")):
        return None
    if "://" in text:
        return None
    parts = text.split("|")
    if len(parts) != 3:
        return None
    name, size, file_hash = parts[0].strip(), parts[1].strip(), parts[2].strip().upper()
    if not name or not size.isdigit():
        return None
    if len(file_hash) == 40:
        return parse_pikpak_sha(f"PikPak://{name}|{size}|{file_hash}")
    if len(file_hash) == 32:
        uri = build_ed2k_uri(name, size, file_hash)
        return {
            "type": "url",
            "url": uri,
            "name": unquote(name),
            "size": size,
            "hash": file_hash,
            "uri": uri,
        }
    return None


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
    if "|" in text:
        return parse_pipe_code(text)
    return None


def _hash_entry_from_parsed(parsed: dict[str, Any], *, source: str) -> dict[str, Any]:
    entry = {
        "kind": "pikpak_sha" if parsed["type"] == "sha" else "ed2k",
        "name": parsed.get("name", ""),
        "size": parsed.get("size", ""),
        "hash": parsed.get("hash", ""),
        "uri": parsed.get("uri", ""),
        "source": source,
    }
    return entry


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
    for match in PIPE_CODE_RE.findall(text or ""):
        name, size, file_hash = match
        if len(file_hash) != 40:
            continue
        parsed = parse_pikpak_sha(f"PikPak://{name}|{size}|{file_hash}")
        if parsed and parsed["uri"] not in seen:
            seen.add(parsed["uri"])
            out.append(parsed["uri"])
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
    for match in re.findall(r'ed2k://[^"\s<>]+', text or "", flags=re.IGNORECASE):
        parsed = parse_ed2k(match)
        if parsed and parsed["uri"] not in seen:
            seen.add(parsed["uri"])
            out.append(parsed["uri"])
    for match in PIPE_CODE_RE.findall(text or ""):
        name, size, file_hash = match
        if len(file_hash) != 32:
            continue
        uri = build_ed2k_uri(name, size, file_hash)
        if uri not in seen:
            seen.add(uri)
            out.append(uri)
    return out


def extract_hash_entries(text: str) -> list[dict[str, Any]]:
    """Collect labeled hash / 特征码 values from post body."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for match in HASH_LABEL_RE.finditer(text or ""):
        file_hash = match.group(1).upper()
        if file_hash in seen:
            continue
        seen.add(file_hash)
        if len(file_hash) == 40:
            algo = "gcid"
            kind = "hash_label_gcid"
        elif len(file_hash) == 32:
            algo = "ed2k"
            kind = "hash_label_ed2k"
        else:
            algo = "unknown"
            kind = "hash_label"
        out.append({
            "kind": kind,
            "hash": file_hash,
            "algo": algo,
            "label": match.group(0).strip()[:120],
            "source": "forum_hash_label",
        })
    return out


def collect_alternatives_from_text(text: str) -> dict[str, Any]:
    """Extract ed2k, PikPak feature codes, and hash labels from HTML/text."""
    pikpak_sha = extract_pikpak_shas(text)
    ed2k = extract_ed2k_links(text)
    hash_entries = extract_hash_entries(text)

    # Enrich hash_entries with full pipe codes found in text
    seen_uri: set[str] = set(pikpak_sha)
    seen_uri.update(ed2k)
    for match in PIPE_CODE_RE.findall(text or ""):
        name, size, file_hash = match
        line = f"{name}|{size}|{file_hash}"
        parsed = parse_pipe_code(line)
        if not parsed:
            continue
        uri = parsed.get("uri", "")
        if uri in seen_uri:
            continue
        seen_uri.add(uri)
        hash_entries.append(_hash_entry_from_parsed(parsed, source="forum_pipe_code"))
        if parsed["type"] == "sha":
            pikpak_sha.append(uri)
        else:
            ed2k.append(uri)

    # De-dupe lists while preserving order
    def _dedupe(seq: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for value in seq:
            if value not in seen:
                seen.add(value)
                out.append(value)
        return out

    return {
        "pikpak_sha": _dedupe(pikpak_sha),
        "ed2k": _dedupe(ed2k),
        "hash_entries": hash_entries,
    }
