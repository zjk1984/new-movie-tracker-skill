#!/usr/bin/env bash
# Validation for scripts/setup_forum142_cron.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/scripts/setup_forum142_cron.sh"
WRAPPER="$ROOT/scripts/forum142_batch_run.sh"

if [[ ! -x "$SCRIPT" ]]; then
  echo "[err] missing executable: $SCRIPT" >&2
  exit 1
fi

if [[ ! -x "$WRAPPER" ]]; then
  echo "[err] missing executable: $WRAPPER" >&2
  exit 1
fi

DRY="$("$SCRIPT" --dry-run 2>/dev/null)"
echo "$DRY" | grep -q 'would install forum142 cron line:'
echo "$DRY" | grep -q 'new-movie-tracker-forum142-batch'
echo "$DRY" | grep -q 'forum142_batch_run.sh'
echo "$DRY" | grep -q 'forum142_batch_run.log'
echo "$DRY" | grep -q 'forum-142_YYYY-MM-DD.md'
echo "$DRY" | grep -q '0 14 \* \* \*'
echo "$DRY" | grep -q 'TZ=Asia/Shanghai'

"$SCRIPT" --help | grep -qi 'daily'
"$SCRIPT" --help | grep -qi '14:00'
"$SCRIPT" --help | grep -qi 'bc-d4fb1f8c'

grep -Fq 'new-movie-tracker-forum142-batch' "$SCRIPT"
grep -Fq 'forum142_batch_run.sh' "$SCRIPT"
grep -Fq 'FORUM142_CRON_WEEKDAYS' "$SCRIPT"

echo "[ok] setup_forum142_cron validation passed"
