#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Submit refetched BT/ed2k threads through unified region + JavDB score gates."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from env_utils import load_env_local
from pikpak_auth import resolve_folder
from pikpak_download import save_download_report, submit_downloads
from submit_gate import collect_gated_downloads


def load_threads(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return list(data.get("threads") or [])


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    load_env_local()
    parser = argparse.ArgumentParser(
        description="Submit refetch JSON magnets with content + JavDB score gates",
    )
    parser.add_argument("--input", required=True, help="refetch_result.json or threads list")
    parser.add_argument("--output-dir", default=".", help="Directory for download_report.json")
    parser.add_argument("--folder", default=None, help="PikPak folder (default: saved or My Pack)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print gated eligible/skipped counts",
    )
    parser.add_argument(
        "--matched",
        default="",
        help="Optional last_result.json to enrich href context",
    )
    args = parser.parse_args()

    threads = load_threads(Path(args.input))
    matched_by_href: dict[str, dict] = {}
    if args.matched:
        matched_path = Path(args.matched)
        if matched_path.exists():
            matched = json.loads(matched_path.read_text(encoding="utf-8")).get("matched") or []
            matched_by_href = {m.get("href"): m for m in matched if m.get("href")}

    eligible, skipped = collect_gated_downloads(threads, matched_by_href)
    print(f"[info] gated: eligible={len(eligible)} skipped={len(skipped)}")
    for row in skipped[:10]:
        print(f"  [skip] {row.get('name', '?')[:50]} — {row.get('skip_reason', '?')}")

    if args.dry_run:
        return 0
    if not eligible:
        print("[info] nothing to submit")
        return 0

    ok, total, succeeded, failed = submit_downloads(
        eligible,
        folder=resolve_folder(args.folder),
    )
    out_dir = Path(args.output_dir)
    report_path = out_dir / "download_report.json"
    save_download_report(
        report_path,
        succeeded=succeeded,
        failed=failed,
        folder=resolve_folder(args.folder),
        source=str(Path(args.input)),
    )
    print(f"[done] submitted {ok}/{total}; report={report_path}")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
