#!/usr/bin/env python3
"""Custom forum scan: configurable start page + up to 100 pages, then PikPak/report."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from daily_run import (  # noqa: E402
    DEFAULT_FORUMS,
    maybe_feishu_notify,
    run_download,
    run_scan,
)
from env_utils import load_env_local

SKILL_DIR = Path(__file__).resolve().parent.parent
MAX_PAGES_LIMIT = 100


def clamp_max_pages(value: int) -> int:
    if value < 1:
        raise argparse.ArgumentTypeError("max-pages must be >= 1")
    return min(value, MAX_PAGES_LIMIT)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description=(
            "Custom scan: set forum start page, flip up to 100 pages, "
            "collect posts, then PikPak + report (same pipeline as daily_run)"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("TRACKER_OUTPUT_DIR", str(SKILL_DIR / "data")),
        help="Directory for results, chrome profile, and download_state.json",
    )
    parser.add_argument(
        "--urls",
        nargs="+",
        default=DEFAULT_FORUMS,
        help="Forum URLs to scan (repeatable)",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=1,
        help="First list page to scan per forum (default: 1)",
    )
    parser.add_argument(
        "--max-pages",
        type=clamp_max_pages,
        default=MAX_PAGES_LIMIT,
        help=f"Pages to scan from start-page (default: {MAX_PAGES_LIMIT}, hard cap)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run browser headless (default: true)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Show browser window (for Cloudflare first pass)",
    )
    parser.add_argument(
        "--scan-only",
        action="store_true",
        help="Scan only, skip PikPak download",
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Submit new magnets from existing last_result.json only",
    )
    parser.add_argument(
        "--pikpak-folder",
        default=None,
        help="PikPak target folder (default: saved or My Pack)",
    )
    parser.add_argument(
        "--feishu",
        action="store_true",
        help="Send scan summary to Feishu when FEISHU_* env is configured",
    )
    parser.add_argument(
        "--no-feishu",
        action="store_true",
        help="Disable Feishu notify even if FEISHU_RECEIVE_ID is set",
    )
    args = parser.parse_args()
    if args.no_headless:
        args.headless = False
    if args.start_page < 1:
        print("[err] --start-page must be >= 1", file=sys.stderr)
        return 2

    load_env_local(SKILL_DIR)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    end_page = args.start_page + args.max_pages - 1
    started = datetime.now().isoformat(timespec="seconds")
    print(f"[info] custom_run started at {started}")
    print(f"[info] output dir: {output_dir}")
    print(
        f"[info] forums: {len(args.urls)} | pages {args.start_page}~{end_page} "
        f"({args.max_pages} page(s) each)",
    )

    # Page-range scans ignore post date; content_filter + JavDB gate still apply.
    scan_args = argparse.Namespace(
        urls=args.urls,
        days=1,
        max_pages=args.max_pages,
        headless=args.headless,
        pikpak_folder=args.pikpak_folder,
    )

    rc = 0
    pikpak_ok: int | None = None
    pikpak_total: int | None = None
    if not args.download_only:
        rc = run_scan(
            scan_args,
            output_dir,
            start_page=args.start_page,
            max_pages=args.max_pages,
            no_date_filter=True,
        )
        if rc != 0:
            return rc

    if not args.scan_only:
        dl_rc, pikpak_ok, pikpak_total = run_download(args, output_dir)
        rc = rc or dl_rc

    feishu_enabled = args.feishu or (
        not args.no_feishu and bool(os.environ.get("FEISHU_RECEIVE_ID"))
    )
    maybe_feishu_notify(
        output_dir,
        enabled=feishu_enabled,
        pikpak_ok=pikpak_ok,
        pikpak_total=pikpak_total,
        run_label="custom",
    )
    return rc


if __name__ == "__main__":
    sys.exit(main())
