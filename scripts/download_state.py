# -*- coding: utf-8 -*-
"""Track submitted downloads so daily runs only fetch new content."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

BTIH_RE = re.compile(r"btih:([a-fA-F0-9]+)", re.IGNORECASE)


def extract_btih(magnet: str | None) -> str | None:
    if not magnet:
        return None
    match = BTIH_RE.search(magnet)
    return match.group(1).upper() if match else None


def default_state_path(output_dir: Path | str) -> Path:
    return Path(output_dir) / "download_state.json"


def empty_state() -> dict[str, Any]:
    return {
        "last_run": None,
        "magnets": {},
        "hashes": {},
        "threads": {},
        "av_numbers": {},
    }


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_state()
    if not isinstance(data, dict):
        return empty_state()
    data.setdefault("magnets", {})
    data.setdefault("hashes", {})
    data.setdefault("threads", {})
    data.setdefault("av_numbers", {})
    return data


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def item_thread_key(item: dict[str, Any]) -> str | None:
    href = (item.get("href") or "").strip()
    return href or None


def item_av_number(item: dict[str, Any]) -> str | None:
    av = (item.get("av_number") or "").strip().upper()
    if av:
        return av
    try:
        from javdb_client import extract_av_number
    except ImportError:
        extract_av_number = None  # type: ignore[assignment,misc]
    if extract_av_number is None:
        return None
    for field in ("name", "title", "uri", "url", "magnet"):
        number = extract_av_number(str(item.get(field) or ""))
        if number:
            return number
    return None


def _item_magnet_text(item: dict[str, Any]) -> str:
    return str(
        item.get("magnet")
        or item.get("url")
        or item.get("uri")
        or "",
    )


def _prefer_cnsub_download(
    existing: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """When two download rows share a number, keep the cnsub magnet."""
    from magnet_select import magnet_has_cnsub

    old_mag = _item_magnet_text(existing)
    new_mag = _item_magnet_text(candidate)
    if magnet_has_cnsub(new_mag) and not magnet_has_cnsub(old_mag):
        return candidate
    return existing


def item_download_key(item: dict[str, Any]) -> str | None:
    btih = extract_btih(item.get("url") or item.get("magnet") or item.get("uri") or "")
    if btih:
        return f"btih:{btih}"
    file_hash = (item.get("hash") or "").upper()
    if file_hash:
        return f"hash:{file_hash}"
    uri = (item.get("uri") or item.get("pikpak_sha") or item.get("url") or "").strip()
    return f"uri:{uri}" if uri else None


def is_already_submitted(item: dict[str, Any], state: dict[str, Any]) -> bool:
    key = item_download_key(item)
    if key:
        store = key.split(":", 1)[0]
        bucket = state.get("hashes" if store == "hash" else "magnets", {})
        lookup = key.split(":", 1)[1]
        if lookup in bucket:
            return True
        if store == "uri" and lookup in state.get("magnets", {}):
            return True
    if _thread_dedup_enabled():
        thread_key = item_thread_key(item)
        if thread_key and thread_key in state.get("threads", {}):
            return True
    av = item_av_number(item)
    if av and av in state.get("av_numbers", {}):
        return True
    return False


def _thread_dedup_enabled() -> bool:
    try:
        from submit_gate import thread_dedup_enabled

        return thread_dedup_enabled()
    except ImportError:
        import os

        return os.environ.get("DOWNLOAD_DEDUP_THREADS", "").strip().lower() in {
            "1", "true", "yes", "on",
        }


def filter_new_items(items: list[dict[str, Any]], state: dict[str, Any]) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    seen_av: dict[str, int] = {}
    av_bucket = state.get("av_numbers") or {}

    for item in items:
        av = item_av_number(item)
        if is_already_submitted(item, state):
            key = item_download_key(item)
            if av and av in av_bucket:
                item["skip_reason"] = "repeat_av_number"
            elif key and key.startswith("hash:"):
                item["skip_reason"] = "repeat_hash"
            elif key and key.startswith("btih:"):
                item["skip_reason"] = "repeat_btih"
            elif item_thread_key(item) and item_thread_key(item) in (state.get("threads") or {}):
                item["skip_reason"] = "repeat_thread"
            else:
                item["skip_reason"] = "already_submitted"
            continue

        if av:
            if av in seen_av:
                idx = seen_av[av]
                existing = kept[idx]
                preferred = _prefer_cnsub_download(existing, item)
                if preferred is existing:
                    item["skip_reason"] = "duplicate_av_number"
                else:
                    existing["skip_reason"] = "duplicate_av_number"
                    kept[idx] = preferred
                continue
            seen_av[av] = len(kept)

        kept.append(item)

    return kept


def mark_submitted(
    state: dict[str, Any],
    items: list[dict[str, Any]],
    *,
    when: datetime | None = None,
    source: str = "auto",
) -> None:
    ts = (when or datetime.now()).isoformat(timespec="seconds")
    magnets = state.setdefault("magnets", {})
    hashes = state.setdefault("hashes", {})
    threads = state.setdefault("threads", {})
    av_numbers = state.setdefault("av_numbers", {})
    for item in items:
        uri = item.get("uri") or item.get("pikpak_sha") or item.get("url") or item.get("magnet") or ""
        item_source = item.get("download_method") or item.get("source") or source
        status = item.get("status") or ("manual_download" if item_source == "manual" else "submitted")
        record = {
            "name": item.get("name") or item.get("av_number") or "",
            "title": (item.get("title") or "")[:120],
            "uri": uri,
            "type": item.get("type", "url"),
            "submitted_at": ts,
            "download_method": item_source,
            "status": status,
        }
        key = item_download_key(item)
        if key:
            store, lookup = key.split(":", 1)
            if store == "hash":
                hashes[lookup] = record
            else:
                magnets[lookup] = record
        thread_key = item_thread_key(item)
        if thread_key:
            threads[thread_key] = key or uri
        av = item_av_number(item)
        if av:
            av_numbers[av] = record


def mark_manual_download(
    state_or_path: dict[str, Any] | Path | str,
    target: str,
    *,
    title: str = "",
    av_number: str = "",
    when: datetime | None = None,
) -> dict[str, Any]:
    """Mark an AV number or download URI as manually downloaded by user.

    Can take a state dict or a path to download_state.json. If a path is given,
    loads the state, modifies it, and saves it.
    """
    path: Path | None = None
    if isinstance(state_or_path, (str, Path)):
        path = Path(state_or_path)
        state = load_state(path)
    else:
        state = state_or_path

    target_str = target.strip()
    item: dict[str, Any] = {
        "title": title,
        "download_method": "manual",
        "status": "manual_download",
    }
    target_upper = target_str.upper()
    if target_str.startswith("magnet:") or target_str.startswith("ed2k:"):
        item["uri"] = target_str
        item["url"] = target_str
        if av_number:
            item["av_number"] = av_number.upper()
        else:
            try:
                from javdb_client import extract_av_number

                num = extract_av_number(target_str) or extract_av_number(title)
                if num:
                    item["av_number"] = num
            except ImportError:
                pass
    elif target_str.startswith("http://") or target_str.startswith("https://"):
        item["href"] = target_str
        if av_number:
            item["av_number"] = av_number.upper()
        elif title:
            try:
                from javdb_client import extract_av_number

                num = extract_av_number(title)
                if num:
                    item["av_number"] = num
            except ImportError:
                pass
    else:
        # Treat as AV number or hash/BTIH
        if re.fullmatch(r"[0-9a-fA-F]{40}", target_str):
            item["hash"] = target_str.upper()
            item["uri"] = f"magnet:?xt=urn:btih:{target_str.upper()}"
        else:
            item["av_number"] = target_upper
            item["name"] = target_upper

    mark_submitted(state, [item], when=when, source="manual")

    if path:
        save_state(path, state)
    return state


def touch_run(state: dict[str, Any], *, when: datetime | None = None) -> None:
    state["last_run"] = (when or datetime.now()).isoformat(timespec="seconds")


def main() -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Manage download state and mark manual downloads")
    sub = parser.add_subparsers(dest="command", required=True)

    mark_parser = sub.add_parser("mark-manual", help="Mark an AV number, magnet, or URL as manually downloaded")
    mark_parser.add_argument("target", help="AV number (e.g. ABC-123), magnet URI, or thread URL")
    mark_parser.add_argument("--state-file", default=None, help="Path to download_state.json (default: current directory or data/download_state.json)")
    mark_parser.add_argument("--output-dir", default=None, help="Output directory containing download_state.json")
    mark_parser.add_argument("--title", default="", help="Optional title for the item")
    mark_parser.add_argument("--av-number", default="", help="Optional explicit AV number")

    args = parser.parse_args()
    if args.command == "mark-manual":
        if args.state_file:
            path = Path(args.state_file)
        elif args.output_dir:
            path = default_state_path(args.output_dir)
        else:
            p = Path("download_state.json")
            if not p.exists() and Path("data/download_state.json").exists():
                p = Path("data/download_state.json")
            path = p

        mark_manual_download(path, args.target, title=args.title, av_number=args.av_number)
        print(f"[ok] Marked as manually downloaded in {path}: {args.target}")
        return 0
    return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
