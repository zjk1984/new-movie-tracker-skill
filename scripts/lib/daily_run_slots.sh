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

# Optional override for tests: DAILY_RUN_SLOT_NOW="2026-09-18T06:50:00+08:00"
daily_run_slot_now_epoch() {
  if [[ -n "${DAILY_RUN_SLOT_NOW:-}" ]]; then
    TZ="$DAILY_RUN_SLOT_TZ" date -d "$DAILY_RUN_SLOT_NOW" +%s
  else
    TZ="$DAILY_RUN_SLOT_TZ" date +%s
  fi
}

daily_run_slot_start_epoch() {
  local slot="$1"
  local day="${2:-$(daily_run_slot_today)}"
  TZ="$DAILY_RUN_SLOT_TZ" date -d "${day} ${slot}:00:00" +%s
}

daily_run_next_slot_start_epoch() {
  local slot="$1"
  case "$slot" in
    7)  daily_run_slot_start_epoch 13 ;;
    13) daily_run_slot_start_epoch 20 ;;
    20)
      local tomorrow
      tomorrow="$(TZ="$DAILY_RUN_SLOT_TZ" date -d "$(daily_run_slot_today) +1 day" +%Y-%m-%d)"
      daily_run_slot_start_epoch 7 "$tomorrow"
      ;;
    *)
      echo "[err] unknown slot hour: $slot (expected 7, 13, or 20)" >&2
      return 2
      ;;
  esac
}

# True when supervisor should poll for this slot: from slot start until next slot start.
daily_run_slot_poll_active() {
  local slot="$1"
  local now start end
  now="$(daily_run_slot_now_epoch)"
  start="$(daily_run_slot_start_epoch "$slot")"
  end="$(daily_run_next_slot_start_epoch "$slot")"
  [[ "$now" -ge "$start" && "$now" -lt "$end" ]]
}

# True when slot has not logged today and we are in its poll window (07:00, 13:00, 20:00 start).
daily_run_slot_pending_for_poll() {
  local slot="$1"
  local log_file="${2:-}"
  daily_run_slot_poll_active "$slot" && ! daily_run_slot_ran_today "$slot" "$log_file"
}

# Seconds until the next slot start (07:00, 13:00, 20:00 Beijing); 07:00 tomorrow after 20:00 slot.
seconds_until_next_slot_start() {
  local now today slot start_ts best=-1
  now="$(daily_run_slot_now_epoch)"
  today="$(daily_run_slot_today)"
  for slot in "${DAILY_RUN_SLOTS[@]}"; do
    start_ts="$(daily_run_slot_start_epoch "$slot" "$today")"
    if [[ "$start_ts" -gt "$now" ]]; then
      if [[ "$best" -lt 0 || "$start_ts" -lt "$best" ]]; then
        best="$start_ts"
      fi
    fi
  done
  if [[ "$best" -ge 0 ]]; then
    echo $(( best - now ))
    return 0
  fi
  local tomorrow next_start
  tomorrow="$(TZ="$DAILY_RUN_SLOT_TZ" date -d "${today} +1 day" +%Y-%m-%d)"
  next_start="$(daily_run_slot_start_epoch 7 "$tomorrow")"
  echo $(( next_start - now ))
}
