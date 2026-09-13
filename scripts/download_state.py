# -*- coding: utf-8 -*-
"""Track submitted magnets so daily runs only download new content."""
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
        "threads": {},
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
    data.setdefault("threads", {})
    return data


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def item_thread_key(item: dict[str, Any]) -> str | None:
    href = (item.get("href") or "").strip()
    return href or None


def item_magnet_key(item: dict[str, Any], magnet: str | None = None) -> str | None:
    uri = magnet or item.get("selected_magnet") or ""
    if not uri and item.get("magnets"):
        uri = item["magnets"][0]
    return extract_btih(uri)


def is_already_submitted(item: dict[str, Any], state: dict[str, Any]) -> bool:
    magnet_key = item_magnet_key(item)
    if magnet_key and magnet_key in state.get("magnets", {}):
        return True
    thread_key = item_thread_key(item)
    if thread_key and thread_key in state.get("threads", {}):
        return True
    return False


def filter_new_items(items: list[dict[str, Any]], state: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in items if not is_already_submitted(item, state)]


def mark_submitted(
    state: dict[str, Any],
    items: list[dict[str, Any]],
    *,
    when: datetime | None = None,
) -> None:
    ts = (when or datetime.now()).isoformat(timespec="seconds")
    magnets = state.setdefault("magnets", {})
    threads = state.setdefault("threads", {})
    for item in items:
        magnet = item.get("magnet") or item.get("selected_magnet") or ""
        magnet_key = extract_btih(magnet)
        thread_key = item_thread_key(item)
        record = {
            "name": item.get("name") or item.get("av_number") or "",
            "title": (item.get("title") or "")[:120],
            "magnet": magnet,
            "submitted_at": ts,
        }
        if magnet_key:
            magnets[magnet_key] = record
        if thread_key:
            threads[thread_key] = magnet_key or magnet


def touch_run(state: dict[str, Any], *, when: datetime | None = None) -> None:
    state["last_run"] = (when or datetime.now()).isoformat(timespec="seconds")
