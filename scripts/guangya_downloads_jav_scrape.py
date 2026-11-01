#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scrape JavDB metadata for JAV videos in GuangYa ``downloads`` and upload Jellyfin sidecars.

Metadata layout (flat, directly under the ``downloads`` folder root — same as PikPak PR #122):
  ``downloads/{番号}.nfo``
  ``downloads/{番号}-poster.jpg``
  optional ``downloads/{番号}-fanart.jpg`` with ``--fanart``

Multiple video files with the same 番号 share one NFO and one poster at the root.
**Video files are not moved** (they may stay in nested subfolders).

Defaults to dry-run; pass ``--apply`` to upload sidecars via guangyapan-drive Skill CLI.
Japanese fields in NFO are translated to Chinese (``title_translate`` / ``rss_translate``;
disable with ``TITLE_TRANSLATE=0``).

Requires GuangYa login on the configured Skill profile (``GUANGYAPAN_PROFILE_DIR``).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from env_utils import load_env_local  # noqa: E402
from guangya_cloud_cli import login_status  # noqa: E402
from guangya_cloud_submit_lib import resolve_guangya_parent_id  # noqa: E402
from guangya_downloads_jav_scrape_lib import (  # noqa: E402
    build_root_file_index,
    fetch_cover_bytes,
    group_videos_by_av,
    guangya_folder_from_env,
    iter_guangya_jav_video_files,
    lookup_scrape_metadata,
    plan_sidecars_for_av,
    root_nfo_needs_retranslate,
    upload_sidecar_bytes,
)
from jellyfin_nfo import (  # noqa: E402
    build_movie_nfo_xml,
    canonical_av_number,
    localize_scrape_metadata_zh,
    validate_nfo_xml,
)
from pikpak_downloads_dedupe_lib import pseudo_as_jav_from_env  # noqa: E402


def _ensure_logged_in() -> None:
    code, payload, stderr = login_status()
    logged_in = (payload.get("data") or {}).get("logged_in")
    if code != 0 or logged_in is not True:
        raise RuntimeError(
            "GuangYa not logged in: run guangyapan-drive login on this profile "
            f"(GUANGYAPAN_PROFILE_DIR); login-status={logged_in!r} {stderr or payload}",
        )


def run_scrape(
    *,
    folder: str,
    apply: bool,
    limit: int,
    numbers_filter: set[str] | None,
    skip_existing: bool,
    include_fanart: bool,
    lang: str,
    recursive: bool,
    parent_id_override: str | None = None,
    translate: bool = True,
    refresh_untranslated: bool = False,
) -> dict[str, Any]:
    from javdb_client import JavDBClient

    _ensure_logged_in()

    if parent_id_override:
        downloads_parent = parent_id_override.strip()
    else:
        downloads_parent = resolve_guangya_parent_id(folder, create_if_missing=False)

    pseudo_jav = pseudo_as_jav_from_env(None)
    client = JavDBClient(lang=lang, use_saved_token=True)

    scanned = list(
        iter_guangya_jav_video_files(
            downloads_parent,
            recursive=recursive,
            pseudo_as_jav=pseudo_jav,
        ),
    )
    video_tuples = [
        (
            {"id": row.get("id"), "name": row.get("name")},
            video_parent_id,
        )
        for row, video_parent_id in scanned
    ]
    av_groups = group_videos_by_av(video_tuples, pseudo_as_jav=pseudo_jav)
    if numbers_filter:
        av_groups = {k: v for k, v in av_groups.items() if k in numbers_filter}

    root_existing, root_file_ids = build_root_file_index(downloads_parent)

    stats: dict[str, Any] = {
        "folder": folder,
        "downloads_parent_id": downloads_parent,
        "mode": "apply" if apply else "dry-run",
        "pseudo_as_jav": pseudo_jav,
        "recursive": recursive,
        "translate_zh": translate,
        "videos_seen": len(scanned),
        "jav_videos": sum(len(v) for v in av_groups.values()),
        "av_groups": len(av_groups),
        "planned_nfo": 0,
        "planned_poster": 0,
        "planned_fanart": 0,
        "skipped_existing": 0,
        "refreshed_untranslated_nfo": 0,
        "javdb_errors": 0,
        "uploaded_nfo": 0,
        "uploaded_poster": 0,
        "uploaded_fanart": 0,
        "items": [],
    }

    processed_groups = 0

    for av in sorted(av_groups.keys()):
        videos = av_groups[av]
        plan = plan_sidecars_for_av(
            av,
            downloads_parent,
            existing_names=root_existing,
            include_fanart=include_fanart,
        )
        if not skip_existing:
            plan["needs_nfo"] = True
            plan["needs_poster"] = True
            if include_fanart:
                plan["needs_fanart"] = True
        elif refresh_untranslated and translate and not plan["needs_nfo"]:
            nfo_name = plan["sidecars"]["nfo"]
            if root_nfo_needs_retranslate(nfo_name, root_file_ids=root_file_ids):
                plan["needs_nfo"] = True
                stats["refreshed_untranslated_nfo"] += 1
        if skip_existing and not plan["needs_nfo"] and not plan["needs_poster"]:
            stats["skipped_existing"] += 1
            continue

        item: dict[str, Any] = {
            "av_number": av,
            "metadata_path": f"{folder}/{plan['sidecars']['nfo']}",
            "sidecars": plan["sidecars"],
            "videos": videos,
        }

        try:
            meta = lookup_scrape_metadata(client, av, sleep_fn=time.sleep)
            meta["number"] = canonical_av_number(av)
            if translate:
                meta = localize_scrape_metadata_zh(meta)
            item["title"] = meta.get("title")
            item["release_date"] = meta.get("release_date")
        except Exception as exc:
            stats["javdb_errors"] += 1
            item["error"] = str(exc)
            stats["items"].append(item)
            processed_groups += 1
            if limit > 0 and processed_groups >= limit:
                break
            continue

        nfo_text = build_movie_nfo_xml(meta)
        validate_nfo_xml(nfo_text)
        item["nfo_bytes"] = len(nfo_text.encode("utf-8"))
        cover_url = str(meta.get("cover_url") or "")

        if plan["needs_nfo"]:
            stats["planned_nfo"] += 1
        if plan["needs_poster"]:
            stats["planned_poster"] += 1
        if plan["needs_fanart"] and include_fanart:
            stats["planned_fanart"] += 1

        if apply:
            if plan["needs_nfo"]:
                upload_sidecar_bytes(
                    nfo_text.encode("utf-8"),
                    plan["sidecars"]["nfo"],
                    downloads_parent,
                )
                stats["uploaded_nfo"] += 1
                root_existing.add(plan["sidecars"]["nfo"])
            if plan["needs_poster"] and cover_url:
                poster_name = plan["sidecars"]["poster"]
                try:
                    cover_bytes = fetch_cover_bytes(cover_url)
                    upload_sidecar_bytes(cover_bytes, poster_name, downloads_parent)
                    stats["uploaded_poster"] += 1
                    root_existing.add(poster_name)
                except Exception as cover_exc:
                    item["poster_error"] = str(cover_exc)
            if plan["needs_fanart"] and include_fanart and cover_url:
                try:
                    fanart_bytes = fetch_cover_bytes(cover_url)
                    upload_sidecar_bytes(
                        fanart_bytes,
                        plan["sidecars"]["fanart"],
                        downloads_parent,
                    )
                    stats["uploaded_fanart"] += 1
                    root_existing.add(plan["sidecars"]["fanart"])
                except Exception as exc:
                    item["fanart_error"] = str(exc)

        stats["items"].append(item)
        processed_groups += 1
        if limit > 0 and processed_groups >= limit:
            break

    return stats


def main() -> int:
    load_env_local()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="JavDB scrape → Jellyfin NFO/posters at GuangYa downloads root",
    )
    parser.add_argument(
        "--folder",
        default=None,
        help=f"GuangYa folder name at drive root (default: env or {guangya_folder_from_env()!r})",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Upload sidecars to GuangYa downloads root (default: dry-run)",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max 番号 groups to process (0=all)")
    parser.add_argument("--numbers", nargs="*", default=None, help="Only these 番号 (space-separated)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Upload even when {番号}.nfo / {番号}-poster.jpg already exist",
    )
    parser.add_argument(
        "--refresh-untranslated",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "When sidecars exist, re-upload NFO if title still has Japanese kana "
            "(default: on with --apply, off in dry-run)"
        ),
    )
    parser.add_argument(
        "--fanart",
        action="store_true",
        help="Also upload {番号}-fanart.jpg (same image as poster)",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Do not scan subfolders under downloads",
    )
    parser.add_argument(
        "--no-translate",
        action="store_true",
        help="Skip Japanese→Chinese localization in NFO fields",
    )
    parser.add_argument(
        "--lang",
        default=os.environ.get("JAVDB_LANG", "cn"),
        help="JavDB accept-language (default: cn)",
    )
    parser.add_argument("--json", action="store_true", help="Print stats JSON")
    parser.add_argument(
        "--parent-id",
        default=None,
        help="GuangYa downloads folder id (skip name lookup)",
    )
    args = parser.parse_args()

    folder = (args.folder or guangya_folder_from_env()).strip()
    numbers_filter = {n.upper() for n in args.numbers} if args.numbers else None
    if args.refresh_untranslated is None:
        refresh_untranslated = args.apply and not args.no_translate
    else:
        refresh_untranslated = args.refresh_untranslated

    try:
        stats = run_scrape(
            folder=folder,
            apply=args.apply,
            limit=args.limit,
            numbers_filter=numbers_filter,
            skip_existing=not args.force,
            include_fanart=args.fanart,
            lang=args.lang,
            recursive=not args.no_recursive,
            parent_id_override=args.parent_id,
            translate=not args.no_translate,
            refresh_untranslated=refresh_untranslated,
        )
    except Exception as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 1

    if args.json:
        out = dict(stats)
        for row in out.get("items") or []:
            row.pop("nfo_bytes", None)
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(
            f"[info] folder={stats['folder']!r} mode={stats['mode']} "
            f"av_groups={stats['av_groups']} jav_videos={stats['jav_videos']} "
            f"planned_nfo={stats['planned_nfo']} planned_poster={stats['planned_poster']} "
            f"skipped_existing={stats['skipped_existing']} "
            f"refreshed_untranslated_nfo={stats['refreshed_untranslated_nfo']} "
            f"javdb_errors={stats['javdb_errors']}",
        )
        if stats["mode"] == "apply":
            print(
                f"[info] uploaded nfo={stats['uploaded_nfo']} poster={stats['uploaded_poster']} "
                f"fanart={stats['uploaded_fanart']}",
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
