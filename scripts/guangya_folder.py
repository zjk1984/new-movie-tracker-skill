# -*- coding: utf-8 -*-
"""GuangYa cloud-drive folder names for scheduled JAV / domestic downloads."""
from __future__ import annotations

import os

DEFAULT_GUANGYA_FOLDER = "My Pack"

_JAV_GUANGYA_REGIONS = frozenset({"jav_censored", "uncensored"})


def resolve_cloud_parent_override() -> tuple[str | None, str | None]:
    """``GUANGYA_CLOUD_PARENT`` / ``GUANGYAPAN_CLOUD_PARENT``: folder name or remote id."""
    raw = (
        os.environ.get("GUANGYA_CLOUD_PARENT")
        or os.environ.get("GUANGYAPAN_CLOUD_PARENT")
        or ""
    ).strip()
    if not raw:
        return None, None
    if " " not in raw and (len(raw) > 20 or "_" in raw):
        return None, raw
    return raw, None


def resolve_guangya_folder(explicit: str | None = None, default: str = DEFAULT_GUANGYA_FOLDER) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    env = (
        os.environ.get("GUANGYAPAN_FOLDER")
        or os.environ.get("GUANGYA_FOLDER")
        or ""
    ).strip()
    if env:
        return env
    return default


def resolve_guangya_jav_folder() -> str:
    env = (os.environ.get("GUANGYAPAN_FOLDER_JAV") or os.environ.get("GUANGYA_FOLDER_JAV") or "").strip()
    return env or DEFAULT_GUANGYA_FOLDER


def resolve_guangya_domestic_folder() -> str:
    env = (
        os.environ.get("GUANGYAPAN_FOLDER_DOMESTIC")
        or os.environ.get("GUANGYA_FOLDER_DOMESTIC")
        or ""
    ).strip()
    return env or DEFAULT_GUANGYA_FOLDER


def guangya_folder_for_download_item(item: dict, *, fallback: str | None = None) -> str:
    """Pick GuangYa folder from item region (mirrors PikPak ``folder_for_download_item``)."""
    region = (item.get("region") or item.get("content_region") or "").strip()
    if region in _JAV_GUANGYA_REGIONS:
        return resolve_guangya_jav_folder()
    if region == "domestic_leak":
        return resolve_guangya_domestic_folder()
    if fallback and fallback.strip():
        return fallback.strip()
    return resolve_guangya_folder(default=DEFAULT_GUANGYA_FOLDER)
