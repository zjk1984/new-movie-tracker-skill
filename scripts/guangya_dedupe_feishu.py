#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Send Feishu summary after successful guangya_downloads_dedupe.sh pipeline."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from env_utils import load_env_local

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SUMMARY = SKILL_DIR / "data" / "guangya_dedupe_last_run.json"


def _load_summary(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def main() -> int:
    load_env_local()
    parser = argparse.ArgumentParser(description="Feishu notify for GuangYa dedupe cron")
    parser.add_argument(
        "--summary",
        type=Path,
        default=DEFAULT_SUMMARY,
        help="Pipeline summary JSON written by dedupe + audit steps",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print message body only")
    args = parser.parse_args()

    from feishu_notify import send_guangya_dedupe_done

    summary = _load_summary(args.summary)
    dedupe = summary.get("dedupe") if isinstance(summary.get("dedupe"), dict) else None
    audit = summary.get("audit") if isinstance(summary.get("audit"), dict) else None

    audit_added = audit.get("added_this_run") if audit else summary.get("audit_added")
    audit_report = summary.get("audit_report") or (
        audit.get("report_json") if audit else None
    )
    jav_scrape_ran = bool(summary.get("jav_scrape_ran"))
    jav_scrape_skipped = bool(summary.get("jav_scrape_skipped", not jav_scrape_ran))
    log_path = str(summary.get("log_path") or "data/guangya_dedupe.log")

    if args.dry_run:
        from feishu_notify import format_beijing_time, beijing_now

        stamp = format_beijing_time(beijing_now(), with_label=False)
        print(f"[dry-run] title line: 【GuangYa 06:45 dedupe】{stamp} 北京")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    result = send_guangya_dedupe_done(
        dedupe_stats=dedupe,
        audit_added=int(audit_added) if audit_added is not None else None,
        audit_report_path=str(audit_report) if audit_report else None,
        jav_scrape_ran=jav_scrape_ran,
        jav_scrape_skipped=jav_scrape_skipped,
        log_path=log_path,
    )
    if result is None:
        return 0
    print(f"[ok] feishu dedupe summary sent (code={result.get('code')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
