#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/scripts/cron_pre_wake.sh"
SETUP="$ROOT/scripts/setup_cron.sh"

[[ -x "$SCRIPT" ]] || { echo "[err] missing $SCRIPT" >&2; exit 1; }

"$SCRIPT" --help | grep -q 'dedupe'
"$SCRIPT" --help | grep -q 'daily'

GUANGYA_DRY="$(GUANGYA_DEDUPE_CRON=1 "$SETUP" --dry-run 2>/dev/null)"
echo "$GUANGYA_DRY" | grep -q 'cron_pre_wake.sh dedupe'
echo "$GUANGYA_DRY" | grep -q 'new-movie-tracker-pre-wake-dedupe'
echo "$GUANGYA_DRY" | grep -q 'cron_pre_wake.sh daily 7'
echo "$GUANGYA_DRY" | grep -q 'cron_pre_wake.sh daily 13'
echo "$GUANGYA_DRY" | grep -q 'cron_pre_wake.sh daily 20'
echo "$GUANGYA_DRY" | grep -q '40 6 .* dedupe'
echo "$GUANGYA_DRY" | grep -q '55 6 .* daily 7'
echo "$GUANGYA_DRY" | grep -q '55 12 .* daily 13'
echo "$GUANGYA_DRY" | grep -q '55 19 .* daily 20'

echo "[ok] cron_pre_wake validation passed"
