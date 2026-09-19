#!/usr/bin/env bash
# Checkpoint-safe idle sleep until the next daily_run slot start.
# VM warm-fork/checkpoint restore resets sleep(1) children with full duration;
# recompute remaining time each chunk so the supervisor cannot oversleep a slot.
# Sourced by daily_run_supervisor.sh; tested in tests/test_daily_run_supervisor_idle.sh.
set -euo pipefail

# Return 0 when idle sleep should end: next slot start reached or poll window active.
_daily_run_supervisor_idle_should_wake() {
  local pending_slot

  if [[ "$(seconds_until_next_slot_start)" -le 0 ]]; then
    return 0
  fi

  if declare -F find_pending_poll_slot >/dev/null 2>&1; then
    pending_slot="$(find_pending_poll_slot 2>/dev/null || true)"
    [[ -n "$pending_slot" ]]
  else
    return 1
  fi
}

# First Beijing slot (7|13|20) whose start passed today but has no daily_run.log entry.
daily_run_supervisor_find_missed_slot_today() {
  local run_log="${1:-}"
  local slot now start_ts

  if [[ -z "$run_log" ]]; then
    echo "[err] daily_run_supervisor_find_missed_slot_today: log file path required" >&2
    return 2
  fi

  now="$(daily_run_slot_now_epoch)"
  for slot in "${DAILY_RUN_SLOTS[@]}"; do
    start_ts="$(daily_run_slot_start_epoch "$slot")"
    if [[ "$now" -ge "$start_ts" ]] && ! daily_run_slot_ran_today "$slot" "$run_log"; then
      echo "$slot"
      return 0
    fi
  done
  return 1
}

daily_run_supervisor_idle_sleep_until_next_slot() {
  local chunk_sec="${DAILY_RUN_SUPERVISOR_IDLE_CHUNK_SEC:-60}"
  local heartbeat_sec="${DAILY_RUN_SUPERVISOR_IDLE_HEARTBEAT_SEC:-900}"
  local wait_sec pending_slot sleep_sec now_epoch last_heartbeat_epoch

  wait_sec="$(seconds_until_next_slot_start)"
  last_heartbeat_epoch="$(daily_run_slot_now_epoch)"
  if [[ -n "${DAILY_RUN_SUPERVISOR_IDLE_LOG:-}" ]]; then
    # shellcheck disable=SC2086
    $DAILY_RUN_SUPERVISOR_IDLE_LOG "[info] idle until next slot start; sleeping in ${chunk_sec}s chunks (${wait_sec}s remaining); heartbeat every ${heartbeat_sec}s"
  fi

  while true; do
    wait_sec="$(seconds_until_next_slot_start)"
    if [[ "$wait_sec" -le 0 ]]; then
      return 0
    fi

    if declare -F find_pending_poll_slot >/dev/null 2>&1; then
      pending_slot="$(find_pending_poll_slot 2>/dev/null || true)"
      if [[ -n "$pending_slot" ]]; then
        if [[ -n "${DAILY_RUN_SUPERVISOR_IDLE_LOG:-}" ]]; then
          # shellcheck disable=SC2086
          $DAILY_RUN_SUPERVISOR_IDLE_LOG "[info] poll window active for slot $pending_slot; ending idle sleep"
        fi
        return 0
      fi
    fi

    now_epoch="$(daily_run_slot_now_epoch)"
    if [[ -n "${DAILY_RUN_SUPERVISOR_IDLE_LOG:-}" ]] \
      && [[ $((now_epoch - last_heartbeat_epoch)) -ge heartbeat_sec ]]; then
      last_heartbeat_epoch="$now_epoch"
      # shellcheck disable=SC2086
      $DAILY_RUN_SUPERVISOR_IDLE_LOG "[info] idle heartbeat; ${wait_sec}s until next slot start"
    fi

    sleep_sec="$chunk_sec"
    if [[ "$wait_sec" -lt "$sleep_sec" ]]; then
      sleep_sec="$wait_sec"
    fi
    sleep "$sleep_sec"

    if _daily_run_supervisor_idle_should_wake; then
      if declare -F find_pending_poll_slot >/dev/null 2>&1; then
        pending_slot="$(find_pending_poll_slot 2>/dev/null || true)"
        if [[ -n "$pending_slot" && -n "${DAILY_RUN_SUPERVISOR_IDLE_LOG:-}" ]]; then
          # shellcheck disable=SC2086
          $DAILY_RUN_SUPERVISOR_IDLE_LOG "[info] poll window active for slot $pending_slot after sleep chunk; ending idle sleep"
        fi
      fi
      return 0
    fi
  done
}
