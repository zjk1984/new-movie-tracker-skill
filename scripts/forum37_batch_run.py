#!/usr/bin/env python3
"""Forum-37 batch scan: one command scans the next 20 list pages, auto-advancing."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
DEFAULT_FORUM_URL = "https://www.sehuatang.org/forum-37-1.html"
DEFAULT_INITIAL_PAGE = 960
PAGES_PER_RUN = 20
DEFAULT_FETCH_WORKERS = 5
STATE_FILENAME = "forum37_batch_state.json"


def state_path(output_dir: Path) -> Path:
    return output_dir / STATE_FILENAME


def load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_next_start_page(
    state: dict,
    *,
    initial_page: int,
    set_page: int | None = None,
) -> int:
    if set_page is not None:
        return max(1, set_page)
    saved = state.get("next_start_page")
    if isinstance(saved, int) and saved >= 1:
        return saved
    return max(1, initial_page)


def build_state_after_run(
    *,
    forum_url: str,
    initial_page: int,
    start_page: int,
    max_pages: int,
    previous: dict,
) -> dict:
    end_page = start_page + max_pages - 1
    return {
        "forum_url": forum_url,
        "initial_start_page": initial_page,
        "last_start_page": start_page,
        "last_end_page": end_page,
        "next_start_page": end_page + 1,
        "pages_per_run": max_pages,
        "last_run_at": datetime.now().isoformat(timespec="seconds"),
        "runs_completed": int(previous.get("runs_completed") or 0) + 1,
    }


def run_batch(args: argparse.Namespace) -> int:
    from env_utils import load_env_local

    load_env_local(SKILL_DIR)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_path(output_dir)
    state = load_state(state_file)

    if args.status:
        if not state:
            print(
                f"[info] forum-37 batch: no state file; next run starts at page "
                f"{args.initial_page} (~{args.initial_page + PAGES_PER_RUN - 1})",
            )
            return 0
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0

    if args.reset:
        if state_file.exists():
            state_file.unlink()
        print(f"[ok] forum-37 batch state reset; next run starts at page {args.initial_page}")
        return 0

    start_page = resolve_next_start_page(
        state,
        initial_page=args.initial_page,
        set_page=args.set_page,
    )
    max_pages = args.max_pages
    end_page = start_page + max_pages - 1

    print(f"[info] forum37_batch_run started at {datetime.now().isoformat(timespec='seconds')}")
    print(f"[info] forum-37 pages {start_page}~{end_page} ({max_pages} page(s))")

    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "custom_run.py"),
        "--headless" if args.headless else "--no-headless",
        "--start-page",
        str(start_page),
        "--max-pages",
        str(max_pages),
        "--urls",
        args.forum_url,
    ]
    if args.scan_only:
        cmd.append("--scan-only")
    if args.feishu:
        cmd.append("--feishu")
    if args.no_feishu:
        cmd.append("--no-feishu")
    if args.output_dir:
        cmd.extend(["--output-dir", str(output_dir)])
    cmd.extend(["--batch-mode", "--fetch-workers", str(args.fetch_workers)])

    print("[info] running:", " ".join(cmd))
    rc = subprocess.call(cmd, cwd=str(SKILL_DIR))
    if rc != 0:
        print(f"[err] batch run failed with exit code {rc}", file=sys.stderr)
        return rc

    save_state(
        state_file,
        build_state_after_run(
            forum_url=args.forum_url,
            initial_page=args.initial_page,
            start_page=start_page,
            max_pages=max_pages,
            previous=state,
        ),
    )
    print(
        f"[ok] forum-37 batch done: scanned {start_page}~{end_page}; "
        f"next run starts at page {end_page + 1}",
    )
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description=(
            "Forum-37 batch scan: each run scans the next 20 list pages "
            "(960~979, then 980~999, …). State is saved between runs."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("TRACKER_OUTPUT_DIR", str(SKILL_DIR / "data")),
        help="Directory for results and page cursor state",
    )
    parser.add_argument(
        "--forum-url",
        default=DEFAULT_FORUM_URL,
        help=f"Forum-37 desktop URL (default: {DEFAULT_FORUM_URL})",
    )
    parser.add_argument(
        "--initial-page",
        type=int,
        default=DEFAULT_INITIAL_PAGE,
        help=f"First start page when no state exists (default: {DEFAULT_INITIAL_PAGE})",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=PAGES_PER_RUN,
        help=f"Pages per run (default: {PAGES_PER_RUN})",
    )
    parser.add_argument(
        "--set-page",
        type=int,
        default=None,
        help="Override next start page for this run only (does not read saved state)",
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
        help="Show browser window",
    )
    parser.add_argument(
        "--scan-only",
        action="store_true",
        help="Scan only, skip PikPak download",
    )
    parser.add_argument(
        "--feishu",
        action="store_true",
        help="Send Feishu notify when configured",
    )
    parser.add_argument(
        "--no-feishu",
        action="store_true",
        help="Disable Feishu notify",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show saved page cursor and exit",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear saved page cursor (next run uses --initial-page)",
    )
    parser.add_argument(
        "--fetch-workers",
        type=int,
        default=DEFAULT_FETCH_WORKERS,
        help=(
            f"Parallel thread-fetch workers for batch scan "
            f"(default: {DEFAULT_FETCH_WORKERS})"
        ),
    )
    args = parser.parse_args()
    if args.no_headless:
        args.headless = False
    if args.max_pages < 1:
        print("[err] --max-pages must be >= 1", file=sys.stderr)
        return 2
    if args.initial_page < 1:
        print("[err] --initial-page must be >= 1", file=sys.stderr)
        return 2
    if args.fetch_workers < 1:
        print("[err] --fetch-workers must be >= 1", file=sys.stderr)
        return 2
    return run_batch(args)


if __name__ == "__main__":
    sys.exit(main())
