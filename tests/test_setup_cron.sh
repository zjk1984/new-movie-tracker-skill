#!/usr/bin/env bash
# shellcheck disable=SC2034
# Validation for scripts/setup_cron.sh (cron install + daemon reload).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/scripts/setup_cron.sh"

if [[ ! -x "$SCRIPT" ]]; then
  echo "[err] missing executable: $SCRIPT" >&2
  exit 1
fi

"$SCRIPT" --dry-run | grep -q 'would install cron line(s):'
"$SCRIPT" --dry-run | grep -q '@reboot sleep 30'
"$SCRIPT" --dry-run | grep -q 'new-movie-tracker-daily-reboot'
"$SCRIPT" --help | grep -qi 'restart'
"$SCRIPT" --help | grep -qi '@reboot'

# Restart attempts must appear in priority order.
grep -Fq 'sudo service cron restart' "$SCRIPT"
grep -Fq 'sudo systemctl restart cron' "$SCRIPT"
grep -Fq 'service cron restart' "$SCRIPT"

awk '
  /sudo service cron restart/ { a=1 }
  /sudo systemctl restart cron/ { if (!a) exit 1; b=1 }
  /service cron restart/ && !/sudo service cron restart/ { if (!b) exit 1; c=1 }
  END { exit !(a && b && c) }
' "$SCRIPT"

echo "[ok] setup_cron validation passed"
