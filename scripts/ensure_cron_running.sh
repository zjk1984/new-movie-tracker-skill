#!/usr/bin/env bash
# Ensure cron daemon is running and tracker crontab is loaded.
# Safe to run at container boot (before cron exists), from setup_cron.sh --ensure-only,
# or from the /etc/cron.d health watchdog.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/data/cron_health.log"
WRAPPER="$ROOT/scripts/daily_run.sh"
MARK="# new-movie-tracker-daily"
PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
TZ_NAME="${DAILY_RUN_TZ:-Asia/Shanghai}"

mkdir -p "$ROOT/data"

log_line() {
  printf '%s %s\n' "$(date -Is)" "$*"
}

cron_service_unit() {
  if command -v systemctl >/dev/null 2>&1; then
    if systemctl list-unit-files cron.service >/dev/null 2>&1; then
      echo cron
      return 0
    fi
    if systemctl list-unit-files crond.service >/dev/null 2>&1; then
      echo crond
      return 0
    fi
  fi
  echo ""
}

cron_daemon_active() {
  local unit
  unit="$(cron_service_unit)"
  if [[ -n "$unit" ]] && command -v systemctl >/dev/null 2>&1; then
    if systemctl is-active --quiet "$unit" 2>/dev/null; then
      return 0
    fi
  fi
  if pgrep -x cron >/dev/null 2>&1 || pgrep -x crond >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

run_privileged() {
  local cmd=( "$@" )
  if sudo -n "${cmd[@]}" 2>/dev/null; then
    return 0
  fi
  if [[ "$(id -u)" -eq 0 ]]; then
    "${cmd[@]}"
    return $?
  fi
  return 1
}

start_cron_daemon() {
  local unit
  unit="$(cron_service_unit)"

  if [[ -n "$unit" ]] && command -v systemctl >/dev/null 2>&1; then
    if run_privileged systemctl enable --now "$unit"; then
      log_line "[ok] systemctl enable --now $unit"
      return 0
    fi
    if run_privileged systemctl start "$unit"; then
      log_line "[ok] systemctl start $unit"
      return 0
    fi
  fi

  if command -v service >/dev/null 2>&1; then
    if run_privileged service cron start; then
      log_line "[ok] service cron start"
      return 0
    fi
    if run_privileged service crond start; then
      log_line "[ok] service crond start"
      return 0
    fi
  fi

  log_line "[err] could not start cron daemon (install cron package and retry)"
  return 1
}

tracker_crontab_present() {
  crontab -l 2>/dev/null | grep -Fq "$MARK"
}

upcoming_slot_note() {
  local hour minute now_h now_m slot
  now_h="$(TZ="$TZ_NAME" date +%-H)"
  now_m="$(TZ="$TZ_NAME" date +%-M)"
  for slot in 7 13 20; do
    if (( now_h < slot || (now_h == slot && now_m == 0) )); then
      log_line "[info] next daily slot today: ${slot}:00 $TZ_NAME (cron must be up before then)"
      return 0
    fi
  done
  log_line "[info] all daily slots (07/13/20 $TZ_NAME) have passed for today"
}

{
  log_line "=== ensure_cron_running start (pid $$) ==="

  if cron_daemon_active; then
    log_line "[ok] cron daemon active"
  else
    log_line "[warn] cron daemon not running; attempting start"
    start_cron_daemon || true
    if cron_daemon_active; then
      log_line "[ok] cron daemon active after start"
    else
      log_line "[err] cron daemon still not running"
    fi
  fi

  if tracker_crontab_present; then
    log_line "[ok] tracker crontab loaded ($MARK)"
  else
    log_line "[warn] tracker crontab missing; run ./scripts/setup_cron.sh"
  fi

  upcoming_slot_note

  log_line "=== ensure_cron_running done ==="
} >>"$LOG" 2>&1
