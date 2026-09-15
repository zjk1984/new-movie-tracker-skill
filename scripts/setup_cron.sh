#!/usr/bin/env bash
# Install daily_run cron job (07:00 Asia/Shanghai).
# Usage: ./scripts/setup_cron.sh [--dry-run] [--time HH:MM]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WRAPPER="$ROOT/scripts/daily_run.sh"
MARK="# new-movie-tracker-daily"
TZ_NAME="${DAILY_RUN_TZ:-Asia/Shanghai}"
TIME="${DAILY_RUN_TIME:-07:00}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --time)
      TIME="${2:?missing value for --time}"
      shift 2
      ;;
    -h|--help)
      cat <<EOF
Install cron job for scripts/daily_run.sh.

Default schedule: 07:00 Asia/Shanghai (Beijing time).
Cron expression: 0 7 * * * (with TZ=Asia/Shanghai)

Usage:
  ./scripts/setup_cron.sh [--dry-run] [--time HH:MM]

Environment overrides:
  DAILY_RUN_TZ=Asia/Shanghai
  DAILY_RUN_TIME=07:00
EOF
      exit 0
      ;;
    *)
      echo "[err] unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if ! [[ "$TIME" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]]; then
  echo "[err] invalid --time '$TIME' (expected HH:MM, 24h)" >&2
  exit 1
fi

HOUR="${TIME%%:*}"
MINUTE="${TIME#*:}"
HOUR="${HOUR#0}"
HOUR="${HOUR:-0}"
MINUTE="${MINUTE#0}"
MINUTE="${MINUTE:-0}"

LINE="$MINUTE $HOUR * * * TZ=$TZ_NAME $WRAPPER $MARK"

chmod +x "$WRAPPER"
mkdir -p "$ROOT/data"

if [[ "${DRY_RUN:-0}" == 1 ]]; then
  echo "[dry-run] would install cron line:"
  echo "  $LINE"
  echo "  log: $ROOT/data/daily_run.log"
  exit 0
fi

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
echo "     timezone: $TZ_NAME"
echo "     log: $ROOT/data/daily_run.log"
crontab -l | grep "$MARK" || true
