#!/usr/bin/env python3
"""Daily scheduled scan + incremental PikPak download (new magnets since last run)."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from env_utils import load_env_local

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"

DEFAULT_FORUMS = [
    "https://www.sehuatang.org/forum-2-1.html",
    "https://www.sehuatang.org/forum-95-1.html",
    "https://www.sehuatang.org/forum-142-1.html",
    "https://www.sehuatang.org/forum-103-1.html",
    "https://www.sehuatang.org/forum-37-1.html",
]


def run_scan(
    args: argparse.Namespace,
    output_dir: Path,
    *,
    start_page: int | None = None,
    max_pages: int | None = None,
    no_date_filter: bool = False,
) -> int:
    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "scan.py"),
        "--output-dir",
        str(output_dir),
        "--days",
        str(args.days),
        "--max-pages",
        str(max_pages if max_pages is not None else args.max_pages),
        "--all-posts",
        "--fetch-magnets",
        "--cnsub-priority",
        *sum([["--urls", url] for url in args.urls], []),
    ]
    if start_page is not None:
        cmd.extend(["--start-page", str(start_page)])
    if no_date_filter:
        cmd.append("--no-date-filter")
    if args.headless:
        cmd.append("--headless")
    print("[info] running scan:", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(SKILL_DIR))


def run_download(args: argparse.Namespace, output_dir: Path) -> tuple[int, int | None, int | None]:
    sys.path.insert(0, str(SCRIPTS_DIR))
    from pikpak_auth import resolve_folder
    from pikpak_download import submit_from_result

    result_path = output_dir / "last_result.json"
    if not result_path.exists():
        print(f"[err] scan result missing: {result_path}", file=sys.stderr)
        return 1, None, None
    try:
        ok, total = submit_from_result(
            result_path,
            folder=resolve_folder(args.pikpak_folder),
            today_only=False,
            region_filter=True,
            new_only=True,
        )
    except RuntimeError as exc:
        print(f"[err] pikpak: {exc}", file=sys.stderr)
        return 1, None, None
    print(f"[done] pikpak new-only: {ok}/{total} submitted")
    if ok == total:
        rc = 0
    elif ok > 0:
        rc = 0
        print(f"[warn] pikpak partial success: {ok}/{total}")
    else:
        rc = 1
    return rc, ok, total


def maybe_feishu_notify(
    output_dir: Path,
    *,
    enabled: bool,
    pikpak_ok: int | None = None,
    pikpak_total: int | None = None,
    run_label: str = "daily",
) -> None:
    if not enabled:
        return
    sys.path.insert(0, str(SCRIPTS_DIR))
    from feishu_notify import is_configured, notify_cards

    if not is_configured():
        print("[info] feishu: credentials or FEISHU_RECEIVE_ID not set, skip notify")
        return
    result_path = output_dir / "last_result.json"
    if not result_path.exists():
        print("[warn] feishu: no last_result.json to summarize")
        return
    try:
        report_path = output_dir / "download_report.json"
        _, md_path, md_url = notify_cards(
            [result_path],
            download_report_path=report_path if report_path.exists() else None,
            run_label=run_label,
        )
        print(f"[ok] feishu summary sent; report: {md_path}")
        if md_url:
            print(f"[ok] github: {md_url}")
    except Exception as exc:
        print(f"[warn] feishu notify failed: {exc}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Daily 7am-style run: scan forums and download only new magnets",
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
        help="Forum URLs to scan (default: forum-2/95/142 + forum-103 + forum-37)",
    )
    parser.add_argument("--days", type=int, default=1, help="Recent days to scan (default: 1, today only)")
    parser.add_argument("--max-pages", type=int, default=100, help="Max pages per forum")
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

    load_env_local(SKILL_DIR)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    started = datetime.now().isoformat(timespec="seconds")
    print(f"[info] daily_run started at {started}")
    print(f"[info] output dir: {output_dir}")

    rc = 0
    pikpak_ok: int | None = None
    pikpak_total: int | None = None
    if not args.download_only:
        rc = run_scan(args, output_dir)
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
    )

    return rc


if __name__ == "__main__":
    sys.exit(main())
