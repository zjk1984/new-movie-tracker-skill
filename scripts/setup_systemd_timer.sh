#!/usr/bin/env bash
# Install systemd timer for daily_run (07:00 Asia/Shanghai).
# Usage: ./scripts/setup_systemd_timer.sh [--dry-run] [--time HH:MM]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TZ_NAME="${DAILY_RUN_TZ:-Asia/Shanghai}"
TIME="${DAILY_RUN_TIME:-07:00}"
UNIT_PREFIX="new-movie-tracker-daily"
SERVICE_DST="/etc/systemd/system/${UNIT_PREFIX}.service"
TIMER_DST="/etc/systemd/system/${UNIT_PREFIX}.timer"

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
Install systemd timer for scripts/daily_run.sh.

Default schedule: 07:00 Asia/Shanghai (OnCalendar=*-*-* 07:00:00 with TZ=$TZ_NAME).
Requires root (writes /etc/systemd/system/).

Usage:
  sudo ./scripts/setup_systemd_timer.sh [--dry-run] [--time HH:MM]
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

SERVICE_SRC="$ROOT/scripts/systemd/${UNIT_PREFIX}.service"
TIMER_SRC="$ROOT/scripts/systemd/${UNIT_PREFIX}.timer"
TMP_SERVICE="$(mktemp)"
TMP_TIMER="$(mktemp)"

sed "s|%i|$ROOT|g" "$SERVICE_SRC" > "$TMP_SERVICE"
{
  cat <<EOF
[Unit]
Description=New Movie Tracker daily run at $TIME $TZ_NAME

[Timer]
OnCalendar=*-*-* ${TIME}:00
Timezone=$TZ_NAME
Persistent=true
Unit=${UNIT_PREFIX}.service

[Install]
WantedBy=timers.target
EOF
} > "$TMP_TIMER"

if [[ "${DRY_RUN:-0}" == 1 ]]; then
  echo "[dry-run] would install:"
  echo "  $SERVICE_DST"
  echo "  $TIMER_DST"
  echo "  schedule: OnCalendar=*-*-* ${TIME}:00 (Timezone=$TZ_NAME)"
  echo "  log: $ROOT/data/daily_run.log"
  exit 0
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "[err] run as root: sudo $0" >&2
  exit 1
fi

install -m 644 "$TMP_SERVICE" "$SERVICE_DST"
install -m 644 "$TMP_TIMER" "$TIMER_DST"
systemctl daemon-reload
systemctl enable --now "${UNIT_PREFIX}.timer"

echo "[ok] systemd timer enabled: ${UNIT_PREFIX}.timer"
echo "     schedule: OnCalendar=*-*-* ${TIME}:00 (Timezone=$TZ_NAME)"
echo "     log: $ROOT/data/daily_run.log"
systemctl list-timers "${UNIT_PREFIX}.timer" --no-pager || true

rm -f "$TMP_SERVICE" "$TMP_TIMER"
