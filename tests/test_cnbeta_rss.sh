#!/usr/bin/env bash
# Validation for scripts/cnbeta_rss.sh wrapper and cron integration.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WRAPPER="$ROOT/scripts/cnbeta_rss.sh"
SETUP="$ROOT/scripts/setup_cron.sh"

if [[ ! -f "$WRAPPER" ]]; then
  echo "[err] missing wrapper: $WRAPPER" >&2
  exit 1
fi

chmod +x "$WRAPPER"

grep -Fq 'cnbeta_rss.py' "$WRAPPER"
grep -Fq 'cnbeta_rss.log' "$WRAPPER"
grep -Fq 'Asia/Shanghai' "$WRAPPER"
grep -Fq 'setup_cron.sh' "$WRAPPER"

DRY="$("$SETUP" --dry-run 2>/dev/null)"
echo "$DRY" | grep -q 'new-movie-tracker-cnbeta'
echo "$DRY" | grep -q "$WRAPPER"

# Three Beijing slots × daily + cnbeta = six user crontab lines.
line_count="$(echo "$DRY" | grep -c 'new-movie-tracker-' || true)"
if [[ "$line_count" -lt 6 ]]; then
  echo "[err] expected at least 6 tracker cron lines in dry-run (got $line_count)" >&2
  exit 1
fi

echo "[ok] cnbeta_rss cron wrapper validation passed"
