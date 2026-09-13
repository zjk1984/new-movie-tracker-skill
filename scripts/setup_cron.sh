#!/usr/bin/env bash
# Install daily_run cron job (07:00 local). Usage: ./scripts/setup_cron.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WRAPPER="$ROOT/scripts/daily_run.sh"
MARK="# new-movie-tracker-daily"
LINE="0 7 * * * $WRAPPER $MARK"

chmod +x "$WRAPPER"
mkdir -p "$ROOT/data"

if ! command -v crontab >/dev/null 2>&1; then
  echo "[err] crontab not installed. Install cron (e.g. apt install cron) first."
  exit 1
fi

TMP="$(mktemp)"
crontab -l 2>/dev/null | grep -v "$MARK" > "$TMP" || true
echo "$LINE" >> "$TMP"
crontab "$TMP"
rm -f "$TMP"

echo "[ok] cron installed: $LINE"
echo "     log: $ROOT/data/daily_run.log"
crontab -l | grep "$MARK" || true
