#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GuangYa ``Save`` NFO → resource links (JavDB by 番号, title/body fallbacks)."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote

from env_utils import load_env_local

load_env_local()

from guangya_cloud_cli import find_directory_id, login_status, run_operations
from guangya_downloads_jav_scrape_lib import walk_guangya_tree
from javdb_client import JavDBClient, extract_av_number, magnet_uri, sort_magnets
from jellyfin_nfo import canonical_av_number

LinkSource = Literal["title", "javdb", "body", "none"]

MAGNET_RE = re.compile(r"magnet:\?[^\s<>\"'\]]+", re.IGNORECASE)
HTTP_RE = re.compile(r"https?://[^\s<>\"'\]]+", re.IGNORECASE)
ENCODED_HTTP_RE = re.compile(r"https?%3[aA][^\s<>\"'\]]+", re.IGNORECASE)
COMMENT_RE = re.compile(r"<!--([\s\S]*?)-->", re.MULTILINE)
TITLE_TAG_RE = re.compile(
    r"<(?:title|originaltitle)>([\s\S]*?)</(?:title|originaltitle)>",
    re.IGNORECASE,
)

JAVDB_LOOKUP_DELAY_SEC = float(os.environ.get("JAVDB_LOOKUP_DELAY_SEC", "0.65"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _report_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def nfo_filename_stem(nfo_name: str) -> str:
    base = nfo_name.rsplit("/", 1)[-1]
    if base.lower().endswith(".nfo"):
        return base[:-4]
    return base


def _decode_maybe_url(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    if "%" in text and ("http" in text.lower() or "magnet" in text.lower()):
        try:
            return unquote(text)
        except Exception:
            pass
    return text


def _links_from_text(text: str, *, source: str, out: list[tuple[str, str]]) -> None:
    for m in MAGNET_RE.findall(text):
        out.append((m.strip(), f"{source}:magnet"))
    for u in HTTP_RE.findall(text):
        u = u.strip().rstrip(".,;)")
        if u.lower().startswith("http"):
            out.append((u, f"{source}:http"))
    for enc in ENCODED_HTTP_RE.findall(text):
        dec = _decode_maybe_url(enc)
        if dec.startswith("http"):
            out.append((dec, f"{source}:encoded_http"))


def _dedupe_urls(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for url, hint in pairs:
        key = url.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append((key, hint))
    return out


def parse_links_from_plain_text(text: str, *, source: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    _links_from_text(text or "", source=source, out=found)
    return _dedupe_urls(found)


def parse_links_from_xml_title_fields(content: str) -> list[tuple[str, str]]:
    raw = content or ""
    found: list[tuple[str, str]] = []
    for block in TITLE_TAG_RE.findall(raw):
        text = unescape_xml_text(block)
        _links_from_text(text, source="xml_title", out=found)
        dec = _decode_maybe_url(text)
        if dec != text:
            _links_from_text(dec, source="xml_title:decoded", out=found)
    if not found:
        try:
            root = ET.fromstring(raw.encode("utf-8"))
        except ET.ParseError:
            return []
        for tag in ("title", "originaltitle"):
            el = root.find(tag)
            if el is not None and el.text and el.text.strip():
                body = el.text.strip()
                _links_from_text(body, source=f"tag:{tag}", out=found)
    return _dedupe_urls(found)


def parse_nfo_links_body(content: str) -> list[tuple[str, str]]:
    raw = content or ""
    found: list[tuple[str, str]] = []
    _links_from_text(raw, source="body", out=found)
    for block in COMMENT_RE.findall(raw):
        _links_from_text(block, source="comment", out=found)
    try:
        root = ET.fromstring(raw.encode("utf-8"))
    except ET.ParseError:
        return _dedupe_urls(found)
    for el in root.iter():
        tag = (el.tag or "").split("}")[-1].lower()
        parts: list[str] = []
        if el.text and el.text.strip():
            parts.append(el.text.strip())
        if el.tail and el.tail.strip():
            parts.append(el.tail.strip())
        if parts:
            body = "\n".join(parts)
            _links_from_text(body, source=f"tag:{tag}", out=found)
            dec = _decode_maybe_url(body)
            if dec != body:
                _links_from_text(dec, source=f"tag:{tag}:decoded", out=found)
    return _dedupe_urls(found)


def unescape_xml_text(text: str) -> str:
    return (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
    )


def extract_av_from_title_metadata(content: str | None, nfo_name: str) -> str:
    """番号 from filename stem / ``<title>`` / ``metatubeid`` (no plot body)."""
    stem = nfo_filename_stem(nfo_name)
    for raw in (stem, nfo_name):
        av = extract_av_number(raw)
        if av:
            return canonical_av_number(av)
    if not content:
        return ""
    for block in TITLE_TAG_RE.findall(content):
        av = extract_av_number(unescape_xml_text(block))
        if av:
            return canonical_av_number(av)
    try:
        root = ET.fromstring(content.encode("utf-8"))
    except ET.ParseError:
        return ""
    for el in root.iter():
        tag = (el.tag or "").split("}")[-1].lower()
        if tag == "metatubeid" and el.text:
            text = el.text.strip()
            if ":" in text:
                cand = unquote(text.rsplit(":", 1)[-1])
                av = extract_av_number(cand)
                if av:
                    return canonical_av_number(av)
        if tag in ("title", "originaltitle") and el.text:
            av = extract_av_number(el.text)
            if av:
                return canonical_av_number(av)
    return ""


def display_name_from_metadata(content: str | None, nfo_name: str) -> str:
    if content:
        try:
            root = ET.fromstring(content.encode("utf-8"))
            el = root.find("title")
            if el is not None and el.text and el.text.strip():
                return el.text.strip()
        except ET.ParseError:
            pass
        for block in TITLE_TAG_RE.findall(content):
            text = unescape_xml_text(block).strip()
            if text:
                return text
    return nfo_filename_stem(nfo_name)


def title_local_links(nfo_name: str, content: str | None) -> list[tuple[str, str]]:
    stem = nfo_filename_stem(nfo_name)
    found = parse_links_from_plain_text(f"{nfo_name}\n{stem}", source="filename_title")
    if content:
        found.extend(parse_links_from_xml_title_fields(content))
    return _dedupe_urls(found)


def javdb_links_for_av(
    client: JavDBClient,
    av: str,
    *,
    cache: dict[str, list[str]],
    stats: dict[str, int],
) -> list[str]:
    key = canonical_av_number(av)
    if not key:
        return []
    if key in cache:
        return cache[key]
    try:
        info = client.lookup(key, fetch_magnets=True, best_only=False)
    except Exception:
        info = {}
    urls: list[str] = []
    for mag in sort_magnets(list(info.get("magnet_rows") or [])):
        uri = magnet_uri(mag)
        if uri and uri not in urls:
            urls.append(uri)
    cache[key] = urls
    stats["javdb_lookups"] = stats.get("javdb_lookups", 0) + 1
    if urls:
        stats["javdb_hit_av"] = stats.get("javdb_hit_av", 0) + 1
    time.sleep(JAVDB_LOOKUP_DELAY_SEC)
    return urls


def url_scheme(url: str) -> str:
    lower = (url or "").lower()
    if lower.startswith("magnet:"):
        return "magnet"
    if lower.startswith("http://") or lower.startswith("https://"):
        return "http"
    return "other"


def fetch_nfo_texts(
    nfo_rows: list[dict[str, Any]],
    *,
    batch_size: int = 12,
) -> dict[str, str]:
    out: dict[str, str] = {}
    for i in range(0, len(nfo_rows), batch_size):
        chunk = nfo_rows[i : i + batch_size]
        ops = [
            {
                "id": f"nfo-{row.get('id')}",
                "type": "return_text",
                "remote_id": str(row.get("id") or ""),
            }
            for row in chunk
            if row.get("id")
        ]
        if not ops:
            continue
        code, data, _stderr = run_operations(ops)
        if code != 0:
            continue
        for item in (data.get("data") or {}).get("items") or []:
            result = item.get("result") or {}
            content = str(result.get("content") or "")
            fid = str(result.get("artifact_id") or "").strip()
            if not fid:
                op_id = str(item.get("operation_id") or "")
                if op_id.startswith("nfo-"):
                    fid = op_id[4:]
            if fid:
                out[fid] = content
    return out


def resolve_save_folder_id(name: str = "Save") -> str:
    for candidate in (name, "save", "SAVE"):
        fid = find_directory_id(candidate)
        if fid:
            return str(fid)
    raise SystemExit(f"[err] GuangYa folder not found: {name!r}")


def build_report(
    save_folder_id: str,
    *,
    batch_size: int = 12,
) -> dict[str, Any]:
    all_files = walk_guangya_tree(save_folder_id)
    nfo_rows = [
        row
        for row in all_files
        if str(row.get("name") or "").lower().endswith(".nfo")
    ]

    # Pass 1: 番号 from filename stem only
    av_from_stem: dict[str, str] = {}
    need_title_fetch: list[dict[str, Any]] = []
    for row in nfo_rows:
        fid = str(row.get("id") or "")
        name = str(row.get("name") or "")
        av = extract_av_from_title_metadata(None, name)
        if av:
            av_from_stem[fid] = av
        else:
            need_title_fetch.append(row)

    title_texts = fetch_nfo_texts(need_title_fetch, batch_size=batch_size)

    av_by_fid: dict[str, str] = dict(av_from_stem)
    for row in need_title_fetch:
        fid = str(row.get("id") or "")
        name = str(row.get("name") or "")
        content = title_texts.get(fid, "")
        av = extract_av_from_title_metadata(content or None, name)
        if av:
            av_by_fid[fid] = av

    client = JavDBClient()
    javdb_cache: dict[str, list[str]] = {}
    javdb_stats: dict[str, int] = {}

    records: list[dict[str, Any]] = []
    stats = {
        "title_hit_nfos": 0,
        "javdb_hit_nfos": 0,
        "body_fallback_nfos": 0,
        "no_link_nfos": 0,
        "javdb_lookups": 0,
        "javdb_hit_av": 0,
        "return_text_for_title_av": len(need_title_fetch),
    }

    unique_avs = sorted({av for av in av_by_fid.values() if av})
    print(
        f"[info] javdb prefetch unique_av={len(unique_avs)}",
        flush=True,
    )
    for idx, av in enumerate(unique_avs, start=1):
        if idx % 50 == 0:
            print(f"[info] javdb prefetch {idx}/{len(unique_avs)}", flush=True)
        javdb_links_for_av(client, av, cache=javdb_cache, stats=javdb_stats)

    body_fetch_queue: list[dict[str, Any]] = []
    resolved: list[tuple[dict[str, Any], str | None, LinkSource, list[str]]] = []

    for row in nfo_rows:
        fid = str(row.get("id") or "")
        name = str(row.get("name") or "")
        content = title_texts.get(fid) if fid in title_texts else None
        av = av_by_fid.get(fid, "")

        local = title_local_links(name, content)
        if local:
            urls = [u for u, _ in local]
            resolved.append((row, av or None, "title", urls))
            stats["title_hit_nfos"] += 1
            continue

        if av:
            urls = javdb_cache.get(canonical_av_number(av), [])
            if urls:
                resolved.append((row, av, "javdb", list(urls)))
                stats["javdb_hit_nfos"] += 1
                continue

        body_fetch_queue.append(row)

    body_texts = fetch_nfo_texts(
        [r for r in body_fetch_queue if str(r.get("id") or "") not in title_texts],
        batch_size=batch_size,
    )
    merged_texts = {**title_texts, **body_texts}

    for row in body_fetch_queue:
        fid = str(row.get("id") or "")
        name = str(row.get("name") or "")
        content = merged_texts.get(fid, "")
        if not content:
            code, data, _ = run_operations(
                [{"id": "one", "type": "return_text", "remote_id": fid}],
            )
            if code == 0:
                item = ((data.get("data") or {}).get("items") or [{}])[0]
                content = (item.get("result") or {}).get("content") or ""

        av = av_by_fid.get(fid) or extract_av_from_title_metadata(content or None, name)
        body_pairs = parse_nfo_links_body(content) if content else []
        if body_pairs:
            resolved.append((row, av or None, "body", [u for u, _ in body_pairs]))
            stats["body_fallback_nfos"] += 1
        else:
            resolved.append((row, av or None, "none", []))
            stats["no_link_nfos"] += 1

    stats["javdb_lookups"] = javdb_stats.get("javdb_lookups", 0)
    stats["javdb_unique_av_with_links"] = javdb_stats.get("javdb_hit_av", 0)

    flat_entries: list[dict[str, Any]] = []
    for row, av, source, urls in resolved:
        fid = str(row.get("id") or "")
        name = str(row.get("name") or "")
        content = merged_texts.get(fid) or title_texts.get(fid)
        display = display_name_from_metadata(content, name)
        rec = {
            "name": display,
            "av_number": av,
            "link_source": source,
            "links": urls,
            "source_nfo_name": name,
            "source_nfo_id": fid,
        }
        records.append(rec)
        for url in urls:
            flat_entries.append(
                {
                    "name": display,
                    "av_number": av,
                    "url": url,
                    "url_scheme": url_scheme(url),
                    "link_source": source,
                    "source_nfo_name": name,
                    "source_nfo_id": fid,
                }
            )

    nfos_with_links = sum(1 for r in records if r.get("links"))

    return {
        "report_type": "guangya_save_nfo_links",
        "generated_at_utc": _utc_now(),
        "guangya_folder": "Save",
        "guangya_folder_id": save_folder_id,
        "nfo_files_scanned": len(nfo_rows),
        "nfo_files_with_links": nfos_with_links,
        "entry_count": len(flat_entries),
        "stats": stats,
        "extraction_rules": {
            "av_number": "title/filename/metatubeid first; full body only for link fallback",
            "link_resolution_order": [
                "title-local (filename + <title>)",
                "JavDB magnets by 番号",
                "NFO body parse when 番号 missing or JavDB empty",
            ],
            "javdb_delay_sec": JAVDB_LOOKUP_DELAY_SEC,
        },
        "records": records,
        "entries": flat_entries,
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    stats = report.get("stats") or {}
    lines = [
        f"# GuangYa Save NFO resource links ({path.stem.replace('guangya_save_nfo_links_', '')})",
        "",
        f"- **Generated (UTC):** {report.get('generated_at_utc')}",
        f"- **Save folder id:** `{report.get('guangya_folder_id')}`",
        f"- **NFO scanned:** {report.get('nfo_files_scanned')}",
        f"- **NFO with links:** {report.get('nfo_files_with_links')}",
        f"- **Link rows:** {report.get('entry_count')}",
        f"- **JavDB hit NFOs:** {stats.get('javdb_hit_nfos')}",
        f"- **Title hit NFOs:** {stats.get('title_hit_nfos')}",
        f"- **Body fallback NFOs:** {stats.get('body_fallback_nfos')}",
        f"- **No link NFOs:** {stats.get('no_link_nfos')}",
        "",
        "| av_number | name | url | source | nfo |",
        "|-----------|------|-----|--------|-----|",
    ]
    for row in report.get("entries") or []:
        av = row.get("av_number") or ""
        name = str(row.get("name") or "").replace("|", "\\|")[:80]
        url = str(row.get("url") or "").replace("|", "\\|")
        src = row.get("link_source") or ""
        nfo = str(row.get("source_nfo_name") or "").replace("|", "\\|")
        lines.append(f"| {av} | {name} | {url} | {src} | {nfo} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", default="Save")
    parser.add_argument("--folder-id", default="")
    parser.add_argument("--date", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json-stdout", action="store_true")
    parser.add_argument("--batch-size", type=int, default=12)
    args = parser.parse_args()

    code, _payload, err = login_status()
    if code != 0:
        print(f"[err] GuangYa login failed: {err}", file=sys.stderr)
        return 1

    folder_id = (args.folder_id or "").strip() or resolve_save_folder_id(args.folder)
    report = build_report(folder_id, batch_size=max(1, args.batch_size))

    if args.json_stdout:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    if not args.apply:
        print(
            json.dumps(
                {
                    "mode": "dry-run",
                    "entry_count": report["entry_count"],
                    "nfo_files_scanned": report["nfo_files_scanned"],
                    "stats": report.get("stats"),
                },
                ensure_ascii=False,
            )
        )
        return 0

    root = Path(__file__).resolve().parent.parent
    date = args.date or _report_date()
    json_path = root / "reports" / f"guangya_save_nfo_links_{date}.json"
    md_path = root / "reports" / f"guangya_save_nfo_links_{date}.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown(report, md_path)
    print(f"[ok] wrote {json_path}")
    print(f"[ok] wrote {md_path}")
    print(f"[ok] entries={report['entry_count']}")
    print(f"[ok] stats={json.dumps(report.get('stats'), ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
