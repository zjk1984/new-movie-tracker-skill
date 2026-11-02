#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""List GuangYa Save folder and persist 番号 already on drive (skip cloud-add)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from env_utils import SKILL_DIR, load_env_local  # noqa: E402
from guangya_auth import sync_credentials_from_skill_store  # noqa: E402
from guangya_cloud_cli import login_status  # noqa: E402
from pikpak_guangya_audit import (  # noqa: E402
    guangya_av_map_from_tree,
    walk_guangya_files,
)

DEFAULT_SAVE_FOLDER_ID = "1963910467505319951"
DEFAULT_OUT = SKILL_DIR / "data" / "guangya_save_already_on_drive.json"


def collect_save_inventory(
    parent_id: str,
    *,
    pseudo_as_jav: bool = True,
) -> dict[str, Any]:
    by_av, files = guangya_av_map_from_tree(parent_id, pseudo=pseudo_as_jav)
    av_samples = {av: by_av[av] for av in sorted(by_av)[:20]}
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "guangya_folder": "Save",
        "guangya_folder_id": parent_id,
        "file_count": len(files),
        "av_number_count": len(by_av),
        "av_numbers": sorted(by_av.keys()),
        "av_sample_names": av_samples,
    }


def main() -> int:
    load_env_local()
    parser = argparse.ArgumentParser(description="Inventory Save folder 番号 on GuangYa")
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
        f"[ok] av_numbers={inv['av_number_count']} files={inv['file_count']} → {out}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
