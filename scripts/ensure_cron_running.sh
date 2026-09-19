#!/usr/bin/env bash
# Ensure cron daemon is running and tracker crontab is loaded for the install user.
# Safe to run at container boot (before cron exists), from setup_cron.sh --ensure-only,
# or from the /etc/cron.d health watchdog (runs as the install user, not root).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/data/cron_health.log"
SETUP="$ROOT/scripts/setup_cron.sh"
MARK="# new-movie-tracker-daily"
CNBETA_MARK="# new-movie-tracker-cnbeta"
CRON_USER_FILE="$ROOT/data/cron_install_user"
PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
TZ_NAME="${DAILY_RUN_TZ:-Asia/Shanghai}"

mkdir -p "$ROOT/data"

log_line() {
  printf '%s %s\n' "$(date -Is)" "$*"
}

resolve_cron_install_user() {
  if [[ -f "$CRON_USER_FILE" ]]; then
    tr -d '[:space:]' < "$CRON_USER_FILE"
    return 0
  fi
  if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != root ]]; then
    echo "$SUDO_USER"
    return 0
  fi
  if [[ "$(id -u)" -ne 0 ]]; then
    id -un
    return 0
  fi
  echo "${CRON_INSTALL_USER:-ubuntu}"
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

restart_cron_daemon() {
  if run_privileged service cron restart; then
    log_line "[ok] cron daemon restarted (service cron restart)"
    return 0
  fi
  if run_privileged systemctl restart cron; then
    log_line "[ok] cron daemon restarted (systemctl restart cron)"
    return 0
  fi
  if run_privileged service crond restart; then
    log_line "[ok] cron daemon restarted (service crond restart)"
    return 0
  fi
  if run_privileged systemctl restart crond; then
    log_line "[ok] cron daemon restarted (systemctl restart crond)"
    return 0
  fi
  log_line "[warn] could not restart cron daemon automatically"
  return 1
}

tracker_crontab_list() {
  local user="$1"
  if [[ "$(id -u)" -eq 0 ]]; then
    crontab -u "$user" -l 2>/dev/null || true
    return 0
  fi
  if [[ "$(id -un)" == "$user" ]]; then
    crontab -l 2>/dev/null || true
    return 0
  fi
  return 1
}

tracker_crontab_present() {
  local user="$1"
  local tab
  tab="$(tracker_crontab_list "$user")" || return 1
  echo "$tab" | grep -Fq "$MARK" && echo "$tab" | grep -Fq "$CNBETA_MARK"
}

repair_tracker_crontab() {
  local user="$1"
  log_line "[warn] tracker crontab missing for $user; attempting repair"
  if [[ "$(id -un)" == "$user" ]]; then
    "$SETUP" --repair-crontab
    return $?
  fi
  if [[ "$(id -u)" -eq 0 ]]; then
    sudo -u "$user" "$SETUP" --repair-crontab
    return $?
  fi
  if sudo -n -u "$user" "$SETUP" --repair-crontab; then
    return 0
  fi
  log_line "[err] cannot repair crontab for $user (need root or run as $user)"
  return 1
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
  log_line "=== ensure_cron_running start (pid $$, user $(id -un)) ==="

  install_user="$(resolve_cron_install_user)"
  log_line "[info] cron install user: $install_user"

  cron_was_down=0
  cron_restarted=0
  crontab_repaired=0

  if cron_daemon_active; then
    log_line "[ok] cron daemon active"
  else
    log_line "[warn] cron daemon not running; attempting start"
    cron_was_down=1
    start_cron_daemon || true
    if cron_daemon_active; then
      log_line "[ok] cron daemon active after start"
    else
      log_line "[err] cron daemon still not running"
    fi
  fi

  if tracker_crontab_present "$install_user"; then
    log_line "[ok] tracker crontab loaded for $install_user ($MARK, $CNBETA_MARK)"
  else
    if repair_tracker_crontab "$install_user"; then
      crontab_repaired=1
      if tracker_crontab_present "$install_user"; then
        log_line "[ok] tracker crontab repaired for $install_user"
      else
        log_line "[err] tracker crontab repair did not load daily/cnbeta marks for $install_user"
      fi
    else
      log_line "[err] tracker crontab repair failed for $install_user"
    fi
  fi

  if [[ "$cron_was_down" -eq 1 || "$crontab_repaired" -eq 1 ]]; then
    if restart_cron_daemon; then
      cron_restarted=1
    fi
  fi

  upcoming_slot_note

  log_line "=== ensure_cron_running done (cron_restarted=$cron_restarted crontab_repaired=$crontab_repaired) ==="
} >>"$LOG" 2>&1
