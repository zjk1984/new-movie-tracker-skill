#!/usr/bin/env bash
# Slot detection for daily_run.sh — which Beijing slots (07/13/20) already ran today.
# Sourced by daily_run_supervisor.sh and tests/test_daily_run_slots.sh.
set -euo pipefail

DAILY_RUN_SLOTS=(7 13 20)
DAILY_RUN_SLOT_TZ="${DAILY_RUN_SLOT_TZ:-Asia/Shanghai}"
DAILY_RUN_START_RE='^===== ([0-9]{4}-[0-9]{2}-[0-9]{2}T[^ ]+) daily_run\.sh start'

daily_run_slot_today() {
  TZ="$DAILY_RUN_SLOT_TZ" date +%Y-%m-%d
}

daily_run_slot_hour_in_window() {
  local slot="$1"
  local hour="$2"
  case "$slot" in
    7)  [[ "$hour" -ge 7 && "$hour" -lt 13 ]] ;;
    13) [[ "$hour" -ge 13 && "$hour" -lt 20 ]] ;;
    20) [[ "$hour" -ge 20 ]] ;;
    *)
      echo "[err] unknown slot hour: $slot (expected 7, 13, or 20)" >&2
      return 2
      ;;
  esac
}

daily_run_slot_in_active_window() {
  local slot="$1"
  local now_hour
  now_hour="$(TZ="$DAILY_RUN_SLOT_TZ" date +%-H)"
  daily_run_slot_hour_in_window "$slot" "$now_hour"
}

# Return 0 if daily_run.sh start for slot (7|13|20) appears in log on today's Beijing date.
daily_run_slot_ran_today() {
  local slot="$1"
  local log_file="${2:-}"
  local today="${3:-}"

  if [[ -z "$log_file" ]]; then
    echo "[err] daily_run_slot_ran_today: log file path required" >&2
    return 2
  fi

  [[ -f "$log_file" ]] || return 1
  today="${today:-$(daily_run_slot_today)}"

  local line ts bj_date bj_hour
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ $DAILY_RUN_START_RE ]]; then
      ts="${BASH_REMATCH[1]}"
      if ! bj_date="$(TZ="$DAILY_RUN_SLOT_TZ" date -d "$ts" +%Y-%m-%d 2>/dev/null)"; then
        continue
      fi
      if ! bj_hour="$(TZ="$DAILY_RUN_SLOT_TZ" date -d "$ts" +%-H 2>/dev/null)"; then
        continue
      fi
      if [[ "$bj_date" == "$today" ]] && daily_run_slot_hour_in_window "$slot" "$bj_hour"; then
        return 0
      fi
    fi
  done < "$log_file"
  return 1
}

daily_run_slot_pending_in_window() {
  local slot="$1"
  local log_file="${2:-}"
  daily_run_slot_in_active_window "$slot" && ! daily_run_slot_ran_today "$slot" "$log_file"
}
