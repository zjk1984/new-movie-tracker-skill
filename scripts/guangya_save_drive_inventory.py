#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""List GuangYa Save folder — 番号 with **video** on drive (skip cloud-add)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from env_utils import SKILL_DIR, load_env_local  # noqa: E402
from guangya_auth import sync_credentials_from_skill_store  # noqa: E402
from guangya_cloud_cli import login_status  # noqa: E402
from javdb_client import extract_all_av_numbers, extract_av_number  # noqa: E402
from jellyfin_nfo import canonical_av_number  # noqa: E402
from pikpak_guangya_audit import walk_guangya_files  # noqa: E402
from pikpak_downloads_dedupe_lib import av_number_for_jav_dedupe  # noqa: E402

DEFAULT_SAVE_FOLDER_ID = "1963910467505319951"
DEFAULT_OUT = SKILL_DIR / "data" / "guangya_save_already_on_drive.json"

VIDEO_EXTENSIONS = frozenset({
    "mp4", "mkv", "avi", "wmv", "m4v", "ts", "m2ts", "iso", "mov", "flv", "webm",
    "mpg", "mpeg", "rmvb", "3gp", "vob",
})

SIDECAR_EXTENSIONS = frozenset({
    "nfo", "jpg", "jpeg", "png", "gif", "bmp", "webp",
    "srt", "ass", "ssa", "sub", "sup", "idx",
    "txt", "url", "html", "htm", "json", "xml",
    "rar", "zip", "7z", "torrent",
})

# Extensionless cloud-add blobs that are large enough to treat as video (bytes).
EXTENSIONLESS_VIDEO_MIN_BYTES = 80 * 1024 * 1024

HYPHEN_AV_RE = re.compile(r"(?i)([A-Z]{2,10})-(\d{2,5})")
COMPACT_AV_RE = re.compile(r"(?i)(?<![A-Z0-9])([A-Z]{2,10})(\d{2,5})(?:[^0-9]|$)")


def av_from_filename(name: str, *, pseudo_as_jav: bool = True) -> str:
    av = av_number_for_jav_dedupe(name, pseudo_as_jav=pseudo_as_jav)
    if av:
        return canonical_av_number(av) or av
    for num in extract_all_av_numbers(name):
        canon = canonical_av_number(num)
        if canon:
            return canon
    raw = extract_av_number(name)
    if raw:
        return canonical_av_number(raw) or raw.upper()
    m = HYPHEN_AV_RE.search(name or "")
    if m:
        return canonical_av_number(f"{m.group(1).upper()}-{m.group(2)}")
    m = COMPACT_AV_RE.search(Path(name or "").stem)
    if m:
        digits = str(int(m.group(2)))
        return canonical_av_number(f"{m.group(1).upper()}-{digits}")
    return ""


def file_extension(name: str) -> str:
    base = (name or "").strip().lower()
    if base.endswith(".nfo"):
        return "nfo"
    if ".poster." in base or base.endswith("-poster.jpg"):
        return "jpg"
    if "." not in Path(base).name:
        return ""
    return Path(base).suffix.lstrip(".").lower()


def is_poster_name(name: str) -> bool:
    n = (name or "").lower()
    return "-poster." in n or n.endswith("poster.jpg") or n.endswith("folder.jpg")


def is_video_file(row: dict[str, Any]) -> bool:
    name = str(row.get("name") or "")
    if is_poster_name(name):
        return False
    ext = file_extension(name)
    if ext in VIDEO_EXTENSIONS:
        return True
    if ext in SIDECAR_EXTENSIONS:
        return False
    size = int(row.get("size") or 0)
    if ext == "" and size >= EXTENSIONLESS_VIDEO_MIN_BYTES:
        av = av_from_filename(name)
        if av:
            return True
    return False


def collect_save_inventory(
    parent_id: str,
    *,
    pseudo_as_jav: bool = True,
) -> dict[str, Any]:
    files = walk_guangya_files(parent_id)
    video_rows: list[dict[str, Any]] = []
    ext_counter: Counter[str] = Counter()
    av_has_video: dict[str, str] = {}
    av_sidecar_only: set[str] = set()
    av_any: set[str] = set()

    for row in files:
        if row.get("type") == "directory":
            continue
        name = str(row.get("name") or "")
        ext = file_extension(name) or "(noext)"
        ext_counter[ext] += 1
        av = av_from_filename(name, pseudo_as_jav=pseudo_as_jav)
        if not av:
            continue
        av_any.add(av)
        if is_video_file(row):
            video_rows.append(row)
            if av not in av_has_video:
                av_has_video[av] = name
        else:
            if av not in av_has_video:
                av_sidecar_only.add(av)

    sidecar_only_av = sorted(av for av in av_sidecar_only if av not in av_has_video)
    av_any_on_save = sorted(av_any)
    video_samples = [
        str(r.get("name") or "")
        for r in sorted(video_rows, key=lambda x: str(x.get("name") or ""))[:5]
    ]
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "guangya_folder": "Save",
        "guangya_folder_id": parent_id,
        "inventory_rules": {
            "video_extensions": sorted(VIDEO_EXTENSIONS),
            "sidecar_extensions": sorted(SIDECAR_EXTENSIONS),
            "extensionless_video_min_bytes": EXTENSIONLESS_VIDEO_MIN_BYTES,
        },
        "remote_file_count": len(files),
        "video_file_count": len(video_rows),
        "extension_breakdown": dict(ext_counter.most_common()),
        "total_av_with_video": len(av_has_video),
        "sidecar_only_av_count": len(sidecar_only_av),
        "total_av_any_on_save": len(av_any_on_save),
        "av_numbers": sorted(av_has_video.keys()),
        "av_any_on_save": av_any_on_save,
        "av_sample_video_names": {k: av_has_video[k] for k in sorted(av_has_video)[:20]},
        "sidecar_only_av": sidecar_only_av,
        "video_path_samples": video_samples,
        "legacy_note": (
            "av_numbers = 番号 with video; av_any_on_save = any file on Save (NFO/sidecar/video) "
            "— use av_any_on_save for cloud-add skip"
        ),
    }


def main() -> int:
    load_env_local()
    parser = argparse.ArgumentParser(description="Inventory Save folder 番号 with video on GuangYa")
    parser.add_argument(
        "--parent-id",
        default=(
            (__import__("os").environ.get("GUANGYA_SAVE_FOLDER_ID") or "").strip()
            or DEFAULT_SAVE_FOLDER_ID
        ),
    )
    parser.add_argument("--output", default=str(DEFAULT_OUT))
    parser.add_argument("--no-auth-sync", action="store_true")
    args = parser.parse_args()

    if not args.no_auth_sync:
        sync_credentials_from_skill_store(force=True)
    code, payload, stderr = login_status()
    logged_in = (payload.get("data") or {}).get("logged_in")
    if code != 0 or logged_in is not True:
        print(f"[err] GuangYa login required: {logged_in!r} {stderr}", file=sys.stderr)
        return 1

    parent_id = str(args.parent_id).strip()
    print(f"[info] walking Save folder {parent_id} …")
    inv = collect_save_inventory(parent_id)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(inv, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"[ok] av_with_video={inv['total_av_with_video']} "
        f"video_files={inv['video_file_count']} "
        f"sidecar_only_av={inv['sidecar_only_av_count']} "
        f"remote_files={inv['remote_file_count']} → {out}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
