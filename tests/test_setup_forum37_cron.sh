#!/usr/bin/env bash
# Validation for scripts/setup_forum37_cron.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/scripts/setup_forum37_cron.sh"
WRAPPER="$ROOT/scripts/forum37_batch_run.sh"

if [[ ! -x "$SCRIPT" ]]; then
  echo "[err] missing executable: $SCRIPT" >&2
  exit 1
fi

if [[ ! -x "$WRAPPER" ]]; then
  echo "[err] missing executable: $WRAPPER" >&2
  exit 1
fi

DRY="$("$SCRIPT" --dry-run 2>/dev/null)"
echo "$DRY" | grep -q 'would install forum37 cron line:'
echo "$DRY" | grep -q 'new-movie-tracker-forum37-batch'
echo "$DRY" | grep -q 'forum37_batch_run.sh'
echo "$DRY" | grep -q 'forum37_batch_run.log'
echo "$DRY" | grep -q '0 18 \* \* 2,4,6'
echo "$DRY" | grep -q 'TZ=Asia/Shanghai'

"$SCRIPT" --help | grep -qi 'Tue/Thu/Sat'
"$SCRIPT" --help | grep -qi '18:00'
"$SCRIPT" --help | grep -qi 'bc-d4fb1f8c'

grep -Fq 'new-movie-tracker-forum37-batch' "$SCRIPT"
grep -Fq 'forum37_batch_run.sh' "$SCRIPT"
grep -Fq 'FORUM37_CRON_WEEKDAYS' "$SCRIPT"

echo "[ok] setup_forum37_cron validation passed"
