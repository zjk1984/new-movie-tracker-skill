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

from scan import DEFAULT_FORUM_URLS as DEFAULT_FORUMS


def run_scan(
    args: argparse.Namespace,
    output_dir: Path,
    *,
    start_page: int | None = None,
    max_pages: int | None = None,
    no_date_filter: bool = False,
    run_label: str = "daily",
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
        "--urls",
        *args.urls,
    ]
    if start_page is not None:
        cmd.extend(["--start-page", str(start_page)])
    if no_date_filter:
        cmd.append("--no-date-filter")
    if run_label:
        cmd.extend(["--run-label", run_label])
    if args.headless:
        cmd.append("--headless")
    if not getattr(args, "serial", False):
        cmd.append("--two-phase")
        list_workers = getattr(args, "list_workers", None)
        fetch_workers = getattr(args, "fetch_workers", None)
        if list_workers is not None:
            cmd.extend(["--list-workers", str(list_workers)])
        if fetch_workers is not None:
            cmd.extend(["--fetch-workers", str(fetch_workers)])
    if getattr(args, "batch_mode", False):
        cmd.append("--batch-mode")
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


def maybe_feishu_scan_done(
    output_dir: Path,
    *,
    enabled: bool,
    run_label: str = "daily",
) -> None:
    if not enabled:
        return
    sys.path.insert(0, str(SCRIPTS_DIR))
    from feishu_notify import is_configured, send_scan_done

    if not is_configured():
        return
    result_path = output_dir / "last_result.json"
    try:
        send_scan_done(result_path, run_label=run_label)
        print("[ok] feishu scan-done card sent")
    except Exception as exc:
        print(f"[warn] feishu scan-done failed: {exc}")


def maybe_feishu_pikpak_done(
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
    from feishu_notify import is_configured, send_pikpak_done

    if not is_configured():
        return
    report_path = output_dir / "download_report.json"
    try:
        send_pikpak_done(
            report_path,
            run_label=run_label,
            pikpak_ok=pikpak_ok,
            pikpak_total=pikpak_total,
        )
        print("[ok] feishu pikpak-done card sent")
    except Exception as exc:
        print(f"[warn] feishu pikpak-done failed: {exc}")


def maybe_feishu_notify(
    output_dir: Path,
    *,
    enabled: bool,
    pikpak_ok: int | None = None,
    pikpak_total: int | None = None,
    run_label: str = "daily",
    existing_report_path: Path | None = None,
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
            existing_report_path=existing_report_path,
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
        help="Forum URLs to scan (default: forum-2/95/142/37 + forum-103 last)",
    )
    parser.add_argument("--days", type=int, default=2, help="Recent days to scan (default: 2)")
    parser.add_argument("--max-pages", type=int, default=10, help="Max pages per forum")
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
    parser.add_argument(
        "--serial",
        action="store_true",
        help="Disable two-phase parallel scan (default uses parallel two-phase)",
    )
    parser.add_argument(
        "--list-workers",
        type=int,
        default=int(os.environ.get("SCAN_LIST_WORKERS", "3")),
        help="Parallel forum list workers (default: 3)",
    )
    parser.add_argument(
        "--fetch-workers",
        type=int,
        default=int(os.environ.get("SCAN_FETCH_WORKERS", "4")),
        help="Parallel thread-fetch workers (default: 4)",
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
    feishu_enabled = args.feishu or (
        not args.no_feishu and bool(os.environ.get("FEISHU_RECEIVE_ID"))
    )

    if not args.download_only:
        rc = run_scan(args, output_dir)
        if rc != 0:
            return rc
        maybe_feishu_scan_done(output_dir, enabled=feishu_enabled, run_label="daily")

    if not args.scan_only:
        dl_rc, pikpak_ok, pikpak_total = run_download(args, output_dir)
        rc = rc or dl_rc
        maybe_feishu_pikpak_done(
            output_dir,
            enabled=feishu_enabled,
            pikpak_ok=pikpak_ok,
            pikpak_total=pikpak_total,
            run_label="daily",
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
