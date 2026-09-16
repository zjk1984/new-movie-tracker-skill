#!/usr/bin/env bash
# Install daily_run cron jobs (07:00 + 13:00 + 20:00 Asia/Shanghai by default).
# Usage: ./scripts/setup_cron.sh [--dry-run] [--time HH:MM] [--time HH:MM ...]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WRAPPER="$ROOT/scripts/daily_run.sh"
MARK="# new-movie-tracker-daily"
REBOOT_MARK="# new-movie-tracker-daily-reboot"
TZ_NAME="${DAILY_RUN_TZ:-Asia/Shanghai}"
TIMES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --time)
      TIMES+=("${2:?missing value for --time}")
      shift 2
      ;;
    -h|--help)
      cat <<EOF
Install cron job(s) for scripts/daily_run.sh.

Default schedule: 07:00, 13:00, and 20:00 Asia/Shanghai (Beijing time).
Requires system timezone Asia/Shanghai (Vixie cron uses system local time).
After install, attempts to restart the cron daemon automatically (required on some VMs).
Also installs an @reboot line to restart cron ~30s after boot (fixes post-reboot missed runs).

Usage:
  ./scripts/setup_cron.sh [--dry-run] [--time HH:MM] [--time HH:MM ...]

  Repeat --time to override defaults, e.g.:
    ./scripts/setup_cron.sh --time 07:00 --time 13:00 --time 20:00

Environment overrides:
  DAILY_RUN_TZ=Asia/Shanghai
  DAILY_RUN_TIMES=07:00,13:00,20:00
EOF
      exit 0
      ;;
    *)
      echo "[err] unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ${#TIMES[@]} -eq 0 ]]; then
  # shellcheck disable=SC2206
  TIMES=(${DAILY_RUN_TIMES:-07:00,13:00,20:00})
fi

# Normalize comma-separated env values and dedupe while preserving order.
normalize_times() {
  local raw joined="" time seen="|"
  for raw in "${TIMES[@]}"; do
    joined="${joined},${raw}"
  done
  joined="${joined#,}"
  joined="${joined//,/ }"
  TIMES=()
  for time in $joined; do
    time="${time// /}"
    [[ -z "$time" ]] && continue
    if [[ "$seen" != *"|$time|"* ]]; then
      TIMES+=("$time")
      seen="${seen}${time}|"
    fi
  done
}

normalize_times

cron_line_for_time() {
  local time="$1"
  if ! [[ "$time" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]]; then
    echo "[err] invalid time '$time' (expected HH:MM, 24h)" >&2
    return 1
  fi
  local hour="${time%%:*}"
  local minute="${time#*:}"
  hour="${hour#0}"
  hour="${hour:-0}"
  minute="${minute#0}"
  minute="${minute:-0}"
  echo "$minute $hour * * * TZ=$TZ_NAME $WRAPPER $MARK"
}

cron_reboot_line() {
  echo "@reboot sleep 30 && (sudo service cron restart || sudo systemctl restart cron || service cron restart) $REBOOT_MARK"
}

is_tracker_cron_line() {
  local line="$1"
  [[ "$line" == *"$WRAPPER"* ]] || [[ "$line" == *"$MARK"* ]] || [[ "$line" == *"$REBOOT_MARK"* ]]
}

restart_cron_daemon() {
  if sudo service cron restart 2>/dev/null; then
    echo "[ok] cron daemon restarted (sudo service cron restart)"
    return 0
  fi
  if sudo systemctl restart cron 2>/dev/null; then
    echo "[ok] cron daemon restarted (sudo systemctl restart cron)"
    return 0
  fi
  if service cron restart 2>/dev/null; then
    echo "[ok] cron daemon restarted (service cron restart)"
    return 0
  fi
  echo "[warn] could not restart cron daemon automatically; run manually: sudo service cron restart" >&2
  return 1
}

chmod +x "$WRAPPER"
mkdir -p "$ROOT/data"

lines=("$(cron_reboot_line)")
for time in "${TIMES[@]}"; do
  lines+=("$(cron_line_for_time "$time")")
done

if [[ "${DRY_RUN:-0}" == 1 ]]; then
  echo "[dry-run] would install cron line(s):"
  for line in "${lines[@]}"; do
    echo "  $line"
  done
  echo "  log: $ROOT/data/daily_run.log"
  exit 0
fi

if ! command -v crontab >/dev/null 2>&1; then
  echo "[err] crontab not installed. Install cron (e.g. apt install cron) first."
  exit 1
fi

TMP="$(mktemp)"
while IFS= read -r line || [[ -n "$line" ]]; do
  if is_tracker_cron_line "$line"; then
    continue
  fi
  printf '%s\n' "$line"
done < <(crontab -l 2>/dev/null || true) > "$TMP"

for line in "${lines[@]}"; do
  echo "$line" >> "$TMP"
done
crontab "$TMP"
rm -f "$TMP"

echo "[ok] cron installed (${#lines[@]} slot(s)):"
for line in "${lines[@]}"; do
  echo "     $line"
done
echo "     timezone: $TZ_NAME (system TZ should match for correct schedule)"
echo "     log: $ROOT/data/daily_run.log"
crontab -l | grep -E 'new-movie-tracker-daily' || true

if ! restart_cron_daemon; then
  echo "[warn] crontab installed but cron may not pick up changes until restart" >&2
fi
