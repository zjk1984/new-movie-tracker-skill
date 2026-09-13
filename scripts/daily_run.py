#!/usr/bin/env python3
"""Daily scheduled scan + incremental PikPak download (new magnets since last run)."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"

DEFAULT_FORUMS = [
    "https://www.sehuatang.org/forum-2-1.html",
    "https://www.sehuatang.org/forum-95-1.html",
    "https://www.sehuatang.org/forum-142-1.html",
    "https://www.sehuatang.org/forum-103-1.html",
    "https://www.sehuatang.org/forum-37-1.html",
]


def load_env_local(skill_dir: Path) -> None:
    env_path = skill_dir / ".env.local"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def run_scan(args: argparse.Namespace, output_dir: Path) -> int:
    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "scan.py"),
        "--output-dir",
        str(output_dir),
        "--days",
        str(args.days),
        "--max-pages",
        str(args.max_pages),
        "--all-posts",
        "--cnsub-priority",
        *sum([["--urls", url] for url in args.urls], []),
    ]
    if args.headless:
        cmd.append("--headless")
    print("[info] running scan:", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(SKILL_DIR))


def run_download(args: argparse.Namespace, output_dir: Path) -> int:
    sys.path.insert(0, str(SCRIPTS_DIR))
    from pikpak_auth import resolve_folder
    from pikpak_download import submit_from_result

    result_path = output_dir / "last_result.json"
    if not result_path.exists():
        print(f"[err] scan result missing: {result_path}", file=sys.stderr)
        return 1
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
        return 1
    print(f"[done] pikpak new-only: {ok}/{total} submitted")
    return 0 if ok == total else 1


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
    if not args.download_only:
        rc = run_scan(args, output_dir)
        if rc != 0:
            return rc

    if not args.scan_only:
        dl_rc = run_download(args, output_dir)
        rc = rc or dl_rc

    return rc


if __name__ == "__main__":
    sys.exit(main())
