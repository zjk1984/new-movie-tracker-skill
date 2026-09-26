#!/usr/bin/env python3
"""Forum-142 batch scan: one command scans the next 10 list pages, auto-advancing.

Scheduled via scripts/setup_forum142_cron.sh (default daily 14:00 Asia/Shanghai).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
REPORTS_DIR = SKILL_DIR / "reports"
DEFAULT_FORUM_URL = "https://www.sehuatang.net/forum-142-1.html"
DEFAULT_INITIAL_PAGE = 200
PAGES_PER_RUN = 10
DEFAULT_FETCH_WORKERS = 5
STATE_FILENAME = "forum142_batch_state.json"


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


def forum142_report_path(*, reports_dir: Path | None = None, when: datetime | None = None) -> Path:
    out = reports_dir or REPORTS_DIR
    out.mkdir(parents=True, exist_ok=True)
    date_str = (when or datetime.now()).strftime("%Y-%m-%d")
    return out / f"forum-142_{date_str}.md"


def _parse_result_scan_time(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def load_fresh_batch_result(
    result_path: Path,
    *,
    not_before: datetime | None = None,
) -> dict | None:
    """Return last_result.json only when it was written during this batch run."""
    if not result_path.exists():
        return None
    try:
        data = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if not_before is not None:
        scan_time = _parse_result_scan_time(data.get("scan_time"))
        if scan_time is None:
            return None
        nb = not_before
        if scan_time.tzinfo is not None and nb.tzinfo is None:
            nb = nb.replace(tzinfo=scan_time.tzinfo)
        elif scan_time.tzinfo is None and nb.tzinfo is not None:
            scan_time = scan_time.replace(tzinfo=nb.tzinfo)
        if scan_time < nb:
            return None
    return data


def load_fresh_download_report(
    download_report_path: Path,
    *,
    not_before: datetime | None = None,
    matched_total: int = 0,
) -> dict[str, Any]:
    from feishu_notify import load_download_report

    empty = {"succeeded": [], "failed": [], "ok": 0, "failed_count": 0, "total": 0}
    if matched_total <= 0:
        return empty
    if not download_report_path.exists():
        return empty
    report = load_download_report(download_report_path)
    if not_before is not None:
        generated_at = _parse_result_scan_time(report.get("generated_at"))
        if generated_at is None:
            return empty
        nb = not_before
        if generated_at.tzinfo is not None and nb.tzinfo is None:
            nb = nb.replace(tzinfo=generated_at.tzinfo)
        elif generated_at.tzinfo is None and nb.tzinfo is not None:
            generated_at = generated_at.replace(tzinfo=nb.tzinfo)
        if generated_at < nb:
            return empty
    return report


def write_forum142_daily_report(
    output_dir: Path,
    *,
    start_page: int,
    end_page: int,
    batch_state: dict,
    exit_code: int = 0,
    reports_dir: Path | None = None,
    batch_started_at: datetime | None = None,
) -> Path:
    """Write per-run markdown record under reports/forum-142_YYYY-MM-DD.md."""
    out_dir = reports_dir or REPORTS_DIR
    report_path = forum142_report_path(reports_dir=out_dir)
    result_path = output_dir / "last_result.json"
    download_report_path = output_dir / "download_report.json"

    batch_header = (
        f"# Forum-142 批量扫描记录\n\n"
        f"- **生成时间**: {datetime.now().isoformat(timespec='seconds')}\n"
        f"- **页码范围**: {start_page}~{end_page}\n"
        f"- **下次起始页**: {batch_state.get('next_start_page')}\n"
        f"- **累计运行次数**: {batch_state.get('runs_completed')}\n"
        f"- **退出码**: {exit_code}\n\n"
    )

    result_data = load_fresh_batch_result(
        result_path,
        not_before=batch_started_at,
    )
    if result_data is not None:
        try:
            from feishu_notify import analyze_scan
            from run_report import write_run_report

            scan_stats = analyze_scan([result_path], enrich_javdb=False)
            download_report = load_fresh_download_report(
                download_report_path,
                not_before=batch_started_at,
                matched_total=int(scan_stats.get("matched_total") or 0),
            )
            staging_label = f"forum-142-staging-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            staging = write_run_report(
                scan_stats,
                download_report,
                run_label=staging_label,
                reports_dir=out_dir,
                output_dir=output_dir,
            )
            body = staging.path.read_text(encoding="utf-8")
            if staging.path != report_path:
                staging.path.unlink(missing_ok=True)
            for archived in staging.archived_paths:
                if archived.exists() and archived.name.startswith(f"{staging_label}_"):
                    archived.unlink(missing_ok=True)
            report_path.write_text(batch_header + body, encoding="utf-8")
            print(f"[ok] forum-142 report: {report_path}")
            return report_path
        except Exception as exc:
            print(f"[warn] forum-142 report generation failed: {exc}", file=sys.stderr)

    report_path.write_text(
        batch_header + "（无扫描结果文件 last_result.json）\n",
        encoding="utf-8",
    )
    print(f"[ok] forum-142 report (minimal): {report_path}")
    return report_path


def feishu_enabled_for_args(args: argparse.Namespace) -> bool:
    return args.feishu or (
        not args.no_feishu and bool(os.environ.get("FEISHU_RECEIVE_ID"))
    )


def maybe_feishu_forum142_summary(
    output_dir: Path,
    report_path: Path,
    *,
    enabled: bool,
) -> None:
    """Send Feishu summary linking to reports/forum-142_YYYY-MM-DD.md."""
    if not enabled:
        return
    from feishu_notify import is_configured, notify_cards

    if not is_configured():
        print("[info] feishu: credentials or FEISHU_RECEIVE_ID not set, skip notify")
        return
    result_path = output_dir / "last_result.json"
    if not result_path.exists():
        print("[warn] feishu: no last_result.json to summarize")
        return
    try:
        download_report_path = output_dir / "download_report.json"
        _, md_path, md_url = notify_cards(
            [result_path],
            download_report_path=download_report_path if download_report_path.exists() else None,
            existing_report_path=report_path,
        )
        print(f"[ok] feishu summary sent; report: {md_path}")
        if md_url:
            print(f"[ok] github: {md_url}")
    except Exception as exc:
        print(f"[warn] feishu notify failed: {exc}")


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
                f"[info] forum-142 batch: no state file; next run starts at page "
                f"{args.initial_page} (~{args.initial_page + PAGES_PER_RUN - 1})",
            )
            return 0
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0

    if args.reset:
        if state_file.exists():
            state_file.unlink()
        print(f"[ok] forum-142 batch state reset; next run starts at page {args.initial_page}")
        return 0

    start_page = resolve_next_start_page(
        state,
        initial_page=args.initial_page,
        set_page=args.set_page,
    )
    max_pages = args.max_pages
    end_page = start_page + max_pages - 1

    batch_started_at = datetime.now()
    print(f"[info] forum142_batch_run started at {batch_started_at.isoformat(timespec='seconds')}")
    print(f"[info] forum-142 pages {start_page}~{end_page} ({max_pages} page(s))")

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
    if args.no_feishu:
        cmd.append("--no-feishu")
    elif feishu_enabled_for_args(args):
        cmd.extend(["--feishu", "--run-label", "forum-142", "--defer-feishu-summary"])
    if args.output_dir:
        cmd.extend(["--output-dir", str(output_dir)])
    cmd.extend(["--batch-mode", "--fetch-workers", str(args.fetch_workers)])

    print("[info] running:", " ".join(cmd))
    rc = subprocess.call(cmd, cwd=str(SKILL_DIR))
    if rc != 0:
        print(f"[err] batch run failed with exit code {rc}", file=sys.stderr)
        return rc

    new_state = build_state_after_run(
        forum_url=args.forum_url,
        initial_page=args.initial_page,
        start_page=start_page,
        max_pages=max_pages,
        previous=state,
    )
    save_state(state_file, new_state)
    report_path = write_forum142_daily_report(
        output_dir,
        start_page=start_page,
        end_page=end_page,
        batch_state=new_state,
        exit_code=rc,
        batch_started_at=batch_started_at,
    )
    maybe_feishu_forum142_summary(
        output_dir,
        report_path,
        enabled=feishu_enabled_for_args(args),
    )
    print(
        f"[ok] forum-142 batch done: scanned {start_page}~{end_page}; "
        f"next run starts at page {end_page + 1}",
    )
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description=(
            "Forum-142 batch scan: each run scans the next 10 list pages "
            "(200~209, then 210~219, …). State is saved between runs."
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
        help=f"Forum-142 desktop URL (default: {DEFAULT_FORUM_URL})",
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
