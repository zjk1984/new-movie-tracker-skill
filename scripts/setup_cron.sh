#!/usr/bin/env bash
# Install daily_run cron jobs (07:00 + 13:00 + 20:00 Asia/Shanghai by default).
# Usage: ./scripts/setup_cron.sh [--dry-run] [--time HH:MM] [--time HH:MM ...]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WRAPPER="$ROOT/scripts/daily_run.sh"
REBOOT_SCRIPT="$ROOT/scripts/cron_reboot_reload.sh"
MARK="# new-movie-tracker-daily"
REBOOT_MARK="# new-movie-tracker-daily-reboot"
REBOOT_CRON_D="/etc/cron.d/new-movie-tracker-reboot"
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
Also installs a root /etc/cron.d @reboot reload hook (no sudo in the job) and
ensures the cron service is enabled at boot.

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

is_tracker_cron_line() {
  local line="$1"
  [[ "$line" == *"$WRAPPER"* ]] || [[ "$line" == *"$MARK"* ]] || [[ "$line" == *"$REBOOT_MARK"* ]] || [[ "$line" == *"@reboot"* && "$line" == *"new-movie-tracker"* ]]
}

cron_service_unit() {
  if systemctl list-unit-files cron.service >/dev/null 2>&1; then
    echo cron
  elif systemctl list-unit-files crond.service >/dev/null 2>&1; then
    echo crond
  else
    echo ""
  fi
}

ensure_cron_boot_enabled() {
  if ! command -v systemctl >/dev/null 2>&1; then
    echo "[info] systemctl not available; ensure cron starts at boot via your init system"
    return 0
  fi

  local unit
  unit="$(cron_service_unit)"
  if [[ -z "$unit" ]]; then
    echo "[warn] cron systemd unit not found; install cron package (e.g. apt install cron)" >&2
    return 1
  fi

  local state
  state="$(systemctl is-enabled "$unit" 2>/dev/null || echo unknown)"
  case "$state" in
    enabled|static|alias)
      echo "[ok] $unit service enabled at boot ($state)"
      return 0
      ;;
    masked)
      echo "[warn] $unit service is masked; unmask and enable: sudo systemctl unmask $unit && sudo systemctl enable $unit" >&2
      return 1
      ;;
    disabled|disabled-by-failure|generated|indirect|not-found|unknown)
      echo "[warn] $unit service not enabled at boot (is-enabled: $state)" >&2
      if [[ "${DRY_RUN:-0}" == 1 ]]; then
        echo "[dry-run] would run: sudo systemctl enable $unit"
        return 0
      fi
      if sudo -n systemctl enable "$unit" 2>/dev/null; then
        echo "[ok] enabled $unit service at boot"
        return 0
      fi
      echo "[warn] run manually: sudo systemctl enable $unit" >&2
      return 1
      ;;
    *)
      echo "[warn] unexpected is-enabled state for $unit: $state" >&2
      return 1
      ;;
  esac
}

reboot_cron_d_content() {
  cat <<EOF
# Installed by scripts/setup_cron.sh — reload cron after boot so user crontabs apply.
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
@reboot root $REBOOT_SCRIPT
EOF
}

install_reboot_cron_d() {
  local content
  content="$(reboot_cron_d_content)"

  if [[ "${DRY_RUN:-0}" == 1 ]]; then
    echo "[dry-run] would install $REBOOT_CRON_D:"
    while IFS= read -r line; do
      echo "  $line"
    done <<<"$content"
    return 0
  fi

  chmod +x "$REBOOT_SCRIPT"

  if ! sudo -n test -d /etc/cron.d 2>/dev/null; then
    echo "[warn] /etc/cron.d not writable; install root reboot hook manually:" >&2
    echo "$content" >&2
    return 1
  fi

  echo "$content" | sudo tee "$REBOOT_CRON_D" >/dev/null
  sudo chmod 644 "$REBOOT_CRON_D"
  echo "[ok] installed $REBOOT_CRON_D (root @reboot reload, no sudo in job)"
}

restart_cron_daemon() {
  if sudo -n service cron restart 2>/dev/null; then
    echo "[ok] cron daemon restarted (sudo service cron restart)"
    return 0
  fi
  if sudo -n systemctl restart cron 2>/dev/null; then
    echo "[ok] cron daemon restarted (sudo systemctl restart cron)"
    return 0
  fi
  if sudo -n service crond restart 2>/dev/null; then
    echo "[ok] cron daemon restarted (sudo service crond restart)"
    return 0
  fi
  if sudo -n systemctl restart crond 2>/dev/null; then
    echo "[ok] cron daemon restarted (sudo systemctl restart crond)"
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

lines=()
for time in "${TIMES[@]}"; do
  lines+=("$(cron_line_for_time "$time")")
done

if [[ "${DRY_RUN:-0}" == 1 ]]; then
  echo "[dry-run] would install cron line(s):"
  for line in "${lines[@]}"; do
    echo "  $line"
  done
  echo "  log: $ROOT/data/daily_run.log"
  install_reboot_cron_d
  ensure_cron_boot_enabled || true
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

install_reboot_cron_d || true
ensure_cron_boot_enabled || true

if ! restart_cron_daemon; then
  echo "[warn] crontab installed but cron may not pick up changes until restart" >&2
fi
