#!/usr/bin/env bash
# Checkpoint-safe idle sleep until the next daily_run slot start.
# VM warm-fork/checkpoint restore resets sleep(1) children with full duration;
# recompute remaining time each chunk so the supervisor cannot oversleep a slot.
# Sourced by daily_run_supervisor.sh; tested in tests/test_daily_run_supervisor_idle.sh.
set -euo pipefail

daily_run_supervisor_idle_sleep_until_next_slot() {
  local chunk_sec="${DAILY_RUN_SUPERVISOR_IDLE_CHUNK_SEC:-60}"
  local wait_sec pending_slot sleep_sec

  wait_sec="$(seconds_until_next_slot_start)"
  if [[ -n "${DAILY_RUN_SUPERVISOR_IDLE_LOG:-}" ]]; then
    # shellcheck disable=SC2086
    $DAILY_RUN_SUPERVISOR_IDLE_LOG "[info] idle until next slot start; sleeping in ${chunk_sec}s chunks (${wait_sec}s remaining)"
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

    sleep_sec="$chunk_sec"
    if [[ "$wait_sec" -lt "$sleep_sec" ]]; then
      sleep_sec="$wait_sec"
    fi
    sleep "$sleep_sec"
  done
}
