#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FEISHU="$ROOT/scripts/feishu_notify.py"
DEDUPE_FEISHU="$ROOT/scripts/guangya_dedupe_feishu.py"
SUMMARY="$ROOT/scripts/guangya_dedupe_summary.py"

grep -Fq 'def send_guangya_dedupe_done' "$FEISHU"
grep -Fq 'feishu skip: credentials or FEISHU_RECEIVE_ID not set' "$FEISHU"
grep -Fq 'guangya_dedupe_feishu.py' "$ROOT/scripts/guangya_downloads_dedupe.sh"
grep -Fq 'maybe_feishu_dedupe_done' "$ROOT/scripts/guangya_downloads_dedupe.sh"

python3 "$SUMMARY" reset
python3 "$SUMMARY" merge --json '{"dedupe":{"mode":"apply","trashed_ok":8,"trash_candidates":8,"files_seen":1474,"within_groups":2,"cross_groups":6},"audit":{"added_this_run":0,"report_json":"reports/pikpak_guangya_audit_2026-11-01.json"},"audit_report":"reports/pikpak_guangya_audit_2026-11-01.json","jav_scrape_skipped":true}'
out="$(python3 "$DEDUPE_FEISHU" --dry-run 2>&1)"
echo "$out" | grep -q '【GuangYa 06:45 dedupe】'
echo "$out" | grep -q 'trashed_ok\|"dedupe"'

echo "[ok] guangya dedupe feishu validation passed"
