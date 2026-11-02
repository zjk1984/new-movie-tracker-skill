#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Add ``selected_magnet`` per record in guangya_save_nfo_links JSON (+ optional MD)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from env_utils import SKILL_DIR  # noqa: E402
from guangya_save_magnet_pick import pick_best_magnet_uri  # noqa: E402
from jellyfin_nfo import canonical_av_number  # noqa: E402

DEFAULT_REPORT = SKILL_DIR / "reports" / "guangya_save_nfo_links_2026-11-01.json"


def apply_selection_to_report(report: dict[str, Any]) -> dict[str, int]:
    stats = {"records": 0, "selected": 0, "no_links": 0}
    for rec in report.get("records") or []:
        if not isinstance(rec, dict):
            continue
        stats["records"] += 1
        links = [str(u).strip() for u in (rec.get("links") or []) if str(u).strip()]
        if not links:
            rec.pop("selected_magnet", None)
            rec.pop("selected_magnet_meta", None)
            stats["no_links"] += 1
            continue
        hint = str(rec.get("name") or rec.get("source_nfo_name") or rec.get("av_number") or "")
        uri, meta = pick_best_magnet_uri(links, name_hint=hint)
        if uri:
            rec["selected_magnet"] = uri
            rec["selected_magnet_meta"] = meta
            stats["selected"] += 1
    report["magnet_selection"] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "policy": "UC > C > cnsub > plain, then largest size hint in dn/name",
    }
    return stats


def write_markdown_summary(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# GuangYa Save NFO links (selected magnet per 番号)",
        "",
        f"- generated: {report.get('generated_at_utc')}",
        f"- selection: {report.get('magnet_selection', {}).get('policy')}",
        f"- records: {len(report.get('records') or [])}",
        "",
        "| av_number | tier | selected_magnet (prefix) | links |",
        "| --- | --- | --- | --- |",
    ]
    for rec in (report.get("records") or [])[:500]:
        av = canonical_av_number(rec.get("av_number") or "") or "—"
        meta = rec.get("selected_magnet_meta") or {}
        tier = meta.get("tier_label") or "—"
        sel = (rec.get("selected_magnet") or "")[:72]
        nlinks = len(rec.get("links") or [])
        lines.append(f"| {av} | {tier} | `{sel}` | {nlinks} |")
    if len(report.get("records") or []) > 500:
        lines.append("")
        lines.append(f"*(+ {len(report['records']) - 500} rows omitted)*")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Select one magnet per Save NFO report record")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--write-md", action="store_true", help="Regenerate companion .md")
    args = parser.parse_args()

    path = Path(args.report)
    report = json.loads(path.read_text(encoding="utf-8"))
    stats = apply_selection_to_report(report)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"[ok] selected={stats['selected']}/{stats['records']} "
        f"no_links={stats['no_links']} → {path}",
    )
    if args.write_md:
        md_path = path.with_suffix(".md")
        write_markdown_summary(report, md_path)
        print(f"[ok] md → {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
