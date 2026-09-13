# -*- coding: utf-8 -*-
"""Parse PikPak feature codes (特征码), ed2k, magnet links, and BT seed hashes."""
from __future__ import annotations

import html as html_module
import re
from typing import Any
from urllib.parse import quote, unquote

PIKPAK_SHA_TEXT_RE = re.compile(
    r"PikPak://[^|\s<>\"']+\|\d+\|[A-Fa-f0-9]{40}",
    re.IGNORECASE,
)
ED2K_TEXT_RE = re.compile(
    r"ed2k://\|[^|\s<>\"']+\|\d+\|[A-Fa-f0-9]{32}\|/?",
    re.IGNORECASE,
)
ED2K_LOOSE_RE = re.compile(
    r"ed2k://(?:\|[^|\s<>\"'\\]+){3}\|/?",
    re.IGNORECASE,
)
ED2K_IN_ATTR_RE = re.compile(
    r"(?:href|data-clipboard-text|data-url|onclick)=([\"'])(.*?ed2k://.*?)\1",
    re.IGNORECASE | re.DOTALL,
)
ED2K_LABEL_RE = re.compile(
    r"(?:ed2k链接|ED2K链接|ed2k地址|下载链接|迅雷链接|115e?d2k链接)"
    r"[：:\s]*\n?\s*(ed2k://[^\s<\"']+)",
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
# BT seed posts: 【特征全码】/哈希校验 → 40-char SHA1 btih (magnet)
BT_FEATURE_LABEL_RE = re.compile(
    r"(?:【|\[)?"
    r"(?:特征全码|特徵全码|特徵全碼|特征全码|哈希校验|校验码|文件校验|哈希值|效验码|"
    r"文件哈希|磁力哈希|btih|hash)"
    r"(?:】|\])?"
    r"[：:\s]*"
    r"([A-Fa-f0-9]{40})",
    re.IGNORECASE,
)
# Domestic BT posts: 【种子特码】：哈希校验; <40hex>; ;
BT_SEED_SPECIAL_RE = re.compile(
    r"【种子特码】[：:\s]*哈希校验\s*;\s*([A-Fa-f0-9]{40})\s*;",
    re.IGNORECASE,
)
# Same semicolon format without the 【种子特码】 wrapper
BT_HASH_SEMICOLON_RE = re.compile(
    r"哈希校验\s*;\s*([A-Fa-f0-9]{40})\s*;",
    re.IGNORECASE,
)
# PikPak GCID / 秒传 (distinct from BT btih)
GCID_LABEL_RE = re.compile(
    r"(?:GCID|秒传码|秒傳碼|PikPak特征码|PikPak特徵碼)"
    r"[：:\s]*([A-Fa-f0-9]{40})",
    re.IGNORECASE,
)
# Generic 特征码 label — 40 hex treated as btih on BT-style posts
GENERIC_FEATURE_LABEL_RE = re.compile(
    r"(?:【|\[)?(?:特征码|特徵码|特徵碼)(?:】|\])?"
    r"[：:\s]*([A-Fa-f0-9]{40})",
    re.IGNORECASE,
)
NAME_BLOCK_RE = re.compile(
    r"【(?:影片名称|中文片名|文件名称)】[：:\s]*([^\n【\[]+)",
    re.IGNORECASE,
)
SIZE_BLOCK_RE = re.compile(
    r"【(?:影片大小|文件大小|文件容量)】[：:\s]*([^\n【\[]+)",
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
    return f"ed2k://|file|{name}|{size}|{file_hash.upper()}|/"


def _strip_markdown_link(text: str) -> str:
    """Remove [label](url) wrappers sometimes picked up from forum HTML."""
    t = text or ""
    t = re.sub(r"\[([^\]]+)\]\((?:mailto:)?[^)]+\)", r"\1", t)
    return t


def parse_ed2k(value: str) -> dict[str, Any] | None:
    text = _strip_markdown_link((value or "").strip())
    if not text.lower().startswith("ed2k://"):
        return None
    body = text[7:]
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|/"):
        body = body[:-2]
    elif body.endswith("|"):
        body = body[:-1]
    parts = [p.strip() for p in body.split("|") if p.strip()]
    if len(parts) < 3:
        return None
    if parts[0].lower() == "file" and len(parts) >= 4:
        name, size, file_hash = parts[1], parts[2], parts[3].upper()
    else:
        name, size, file_hash = parts[0], parts[1], parts[2].upper()
    if not name or not size.isdigit() or len(file_hash) != 32:
        return None
    uri = build_ed2k_uri(name, size, file_hash)
    return {
        "type": "url",
        "url": uri,
        "name": unquote(name),
        "size": size,
        "hash": file_hash,
        "uri": uri,
    }


def normalize_ed2k_uri(value: str) -> str | None:
    """Return canonical ed2k://|file|name|size|hash|/ or None."""
    parsed = parse_ed2k(value)
    return parsed["uri"] if parsed else None


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


def preprocess_link_text(text: str) -> str:
    """Decode HTML entities / URL encoding before link extraction."""
    if not text:
        return ""
    t = html_module.unescape(text)
    t = unquote(t)
    t = re.sub(r"ed2k\s*:\s*//", "ed2k://", t, flags=re.IGNORECASE)
    return t


def _add_ed2k_candidate(raw: str, seen: set[str], out: list[str]) -> None:
    text = preprocess_link_text(raw).strip().strip("'\"")
    if not text.lower().startswith("ed2k://"):
        return
    # Trim trailing HTML junk
    text = re.split(r'[<"\s]', text, maxsplit=1)[0]
    parsed = parse_ed2k(text)
    if not parsed:
        return
    uri = parsed["uri"]
    if uri not in seen:
        seen.add(uri)
        out.append(uri)


def extract_ed2k_links(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    raw = preprocess_link_text(text or "")

    for pattern in (ED2K_TEXT_RE, ED2K_LOOSE_RE):
        for match in pattern.findall(raw):
            _add_ed2k_candidate(match, seen, out)

    for match in re.findall(r"ed2k://[^\"'\s<>]+", raw, flags=re.IGNORECASE):
        _add_ed2k_candidate(match, seen, out)

    for match in ED2K_IN_ATTR_RE.finditer(text or ""):
        _add_ed2k_candidate(match.group(2), seen, out)

    for match in ED2K_LABEL_RE.finditer(raw):
        _add_ed2k_candidate(match.group(1), seen, out)

    for match in PIPE_CODE_RE.findall(raw):
        name, size, file_hash = match
        if len(file_hash) != 32:
            continue
        uri = build_ed2k_uri(name, size, file_hash)
        if uri not in seen:
            seen.add(uri)
            out.append(uri)
    return out


def normalize_post_text(text: str) -> str:
    """Strip HTML and preserve line breaks for BT seed / hash label parsing."""
    if not text:
        return ""
    t = text
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    t = re.sub(r"(?i)</p>", "\n", t)
    t = re.sub(r"(?i)</div>", "\n", t)
    t = re.sub(r"(?i)</tr>", "\n", t)
    t = re.sub(r"(?i)</li>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html_module.unescape(t)
    t = t.replace("\xa0", " ")
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t


def btih_magnet(file_hash: str, name: str = "") -> str:
    h = file_hash.upper()
    uri = f"magnet:?xt=urn:btih:{h}"
    if name:
        uri += f"&dn={quote(name.strip())}"
    return uri


def _nearest_name_before(text: str, pos: int) -> str:
    """Best-effort title from 【影片名称】 block preceding a hash label."""
    window = text[max(0, pos - 1200):pos]
    names = NAME_BLOCK_RE.findall(window)
    return names[-1].strip() if names else ""


def extract_bt_feature_magnets(text: str) -> tuple[list[str], list[dict[str, Any]]]:
    """
    Parse BT seed post 【特征全码】/哈希校验 → magnet:?xt=urn:btih:...
    Returns (magnet_uris, hash_entries).
    """
    plain = normalize_post_text(text)
    seen: set[str] = set()
    magnets: list[str] = []
    entries: list[dict[str, Any]] = []

    patterns = (
        BT_FEATURE_LABEL_RE,
        GENERIC_FEATURE_LABEL_RE,
        BT_SEED_SPECIAL_RE,
        BT_HASH_SEMICOLON_RE,
    )
    for pattern in patterns:
        for match in pattern.finditer(plain):
            file_hash = match.group(1).upper()
            if file_hash in seen:
                continue
            seen.add(file_hash)
            name = _nearest_name_before(plain, match.start())
            uri = btih_magnet(file_hash, name)
            source = (
                "forum_bt_seed_code"
                if pattern in (BT_SEED_SPECIAL_RE, BT_HASH_SEMICOLON_RE)
                else "forum_bt_feature"
            )
            magnets.append(uri)
            entries.append({
                "kind": "hash_label_btih",
                "hash": file_hash,
                "algo": "btih",
                "name": name,
                "uri": uri,
                "label": match.group(0).strip()[:120],
                "source": source,
            })

    return magnets, entries


def extract_hash_entries(text: str) -> list[dict[str, Any]]:
    """Collect labeled hash / 特征码 values from post body."""
    plain = normalize_post_text(text)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    _, bt_entries = extract_bt_feature_magnets(plain)
    for entry in bt_entries:
        seen.add(entry["hash"])
        out.append(entry)

    for match in GCID_LABEL_RE.finditer(plain):
        file_hash = match.group(1).upper()
        if file_hash in seen:
            continue
        seen.add(file_hash)
        out.append({
            "kind": "hash_label_gcid",
            "hash": file_hash,
            "algo": "gcid",
            "label": match.group(0).strip()[:120],
            "source": "forum_hash_label",
        })

    ed2k_label_re = re.compile(
        r"(?:哈希校验|校验码|文件校验|文件哈希|hash)[：:\s]*([A-Fa-f0-9]{32})",
        re.IGNORECASE,
    )
    for match in ed2k_label_re.finditer(plain):
        file_hash = match.group(1).upper()
        if file_hash in seen:
            continue
        seen.add(file_hash)
        out.append({
            "kind": "hash_label_ed2k",
            "hash": file_hash,
            "algo": "ed2k",
            "label": match.group(0).strip()[:120],
            "source": "forum_hash_label",
        })

    return out


def collect_alternatives_from_text(text: str) -> dict[str, Any]:
    """Extract ed2k, PikPak feature codes, BT feature magnets, and hash labels."""
    plain = normalize_post_text(text)
    pikpak_sha = extract_pikpak_shas(plain)
    ed2k = extract_ed2k_links(plain)
    feature_magnets, _ = extract_bt_feature_magnets(plain)
    hash_entries = extract_hash_entries(plain)

    # Enrich hash_entries with full pipe codes found in text
    seen_uri: set[str] = set(pikpak_sha)
    seen_uri.update(ed2k)
    for match in PIPE_CODE_RE.findall(plain):
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
        "magnets": _dedupe(feature_magnets),
        "pikpak_sha": _dedupe(pikpak_sha),
        "ed2k": _dedupe(ed2k),
        "hash_entries": hash_entries,
    }
