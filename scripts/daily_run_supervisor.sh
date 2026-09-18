#!/usr/bin/env bash
# Long-running supervisor for daily_run on container VMs where cron daemon dies randomly.
# Does NOT depend on cron staying alive for scheduling — sleeps between Beijing slot starts
# (07:00, 13:00, 20:00), polls every 5 min only during each pending slot window, and waits
# while daily_run.sh is already running.
#
# Start in tmux (recommended on cron VM bc-d4fb1f8c):
#   tmux new-session -d -s daily-supervisor -c /workspace \
#     '/workspace/scripts/daily_run_supervisor.sh'
#
# Still runs ensure_cron_running.sh each poll cycle so cron remains best-effort backup.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/daily_run_slots.sh
source "$ROOT/scripts/lib/daily_run_slots.sh"
# shellcheck source=lib/daily_run_supervisor_idle.sh
source "$ROOT/scripts/lib/daily_run_supervisor_idle.sh"

ENSURE="$ROOT/scripts/ensure_cron_running.sh"
DAILY_RUN="$ROOT/scripts/daily_run.sh"
RUN_LOG="$ROOT/data/daily_run.log"
SUP_LOG="$ROOT/data/supervisor.log"
LOCK_DIR="$ROOT/data/supervisor.lock"
POLL_SEC="${DAILY_RUN_SUPERVISOR_POLL_SEC:-300}"
TZ_NAME="${DAILY_RUN_TZ:-Asia/Shanghai}"

mkdir -p "$ROOT/data"

supervisor_log() {
  printf '%s %s\n' "$(TZ="$TZ_NAME" date -Is)" "$*" | tee -a "$SUP_LOG"
}

daily_run_in_progress() {
  pgrep -f '[/ ]scripts/daily_run\.(sh|py)' >/dev/null 2>&1
}

wait_for_daily_run() {
  while daily_run_in_progress; do
    sleep 10
  done
}

run_ensure_cron() {
  if [[ -x "$ENSURE" ]]; then
    "$ENSURE" >> "$SUP_LOG" 2>&1 || supervisor_log "[warn] ensure_cron_running exited non-zero"
  else
    supervisor_log "[warn] missing $ENSURE"
  fi
}

trigger_slot() {
  local slot="$1"
  if daily_run_in_progress; then
    supervisor_log "[info] slot $slot: daily_run already running; skip"
    return 0
  fi
  if daily_run_slot_ran_today "$slot" "$RUN_LOG"; then
    supervisor_log "[info] slot $slot: already logged today; skip"
    return 0
  fi

  supervisor_log "[info] slot $slot: triggering daily_run.sh"
  if "$DAILY_RUN"; then
    supervisor_log "[info] slot $slot: daily_run.sh completed"
  else
    local ec=$?
    supervisor_log "[warn] slot $slot: daily_run.sh failed (exit $ec)"
    return "$ec"
  fi
}

find_pending_poll_slot() {
  local slot
  for slot in "${DAILY_RUN_SLOTS[@]}"; do
    if daily_run_slot_pending_for_poll "$slot" "$RUN_LOG"; then
      echo "$slot"
      return 0
    fi
  done
  return 1
}

maybe_trigger_due_slots() {
  local slot
  slot="$(find_pending_poll_slot || true)"
  if [[ -n "$slot" ]]; then
    trigger_slot "$slot" || true
  fi
}

sleep_until_next_slot() {
  DAILY_RUN_SUPERVISOR_IDLE_LOG=supervisor_log
  export DAILY_RUN_SUPERVISOR_IDLE_LOG
  daily_run_supervisor_idle_sleep_until_next_slot
}

supervisor_cycle() {
  if daily_run_in_progress; then
    supervisor_log "[info] daily_run in progress; waiting for completion"
    wait_for_daily_run
    supervisor_log "[info] daily_run finished"
    return 0
  fi

  local pending_slot
  pending_slot="$(find_pending_poll_slot || true)"
  if [[ -n "$pending_slot" ]]; then
    run_ensure_cron
    maybe_trigger_due_slots
    if daily_run_in_progress; then
      return 0
    fi
    supervisor_log "[info] slot $pending_slot: poll window active; sleeping ${POLL_SEC}s"
    sleep "$POLL_SEC"
    return 0
  fi

  sleep_until_next_slot
}

acquire_lock() {
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "$$" > "$LOCK_DIR/pid"
    return 0
  fi
  if [[ -f "$LOCK_DIR/pid" ]]; then
    local old_pid
    old_pid="$(tr -d '[:space:]' < "$LOCK_DIR/pid" 2>/dev/null || true)"
    if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
      echo "[err] another supervisor is running (pid $old_pid)" >&2
      exit 1
    fi
  fi
  rm -rf "$LOCK_DIR"
  mkdir "$LOCK_DIR"
  echo "$$" > "$LOCK_DIR/pid"
}

release_lock() {
  rm -rf "$LOCK_DIR"
}

trap release_lock EXIT

main_loop() {
  acquire_lock
  supervisor_log "=== daily_run_supervisor start (pid $$, poll=${POLL_SEC}s, TZ=$TZ_NAME) ==="

  while true; do
    supervisor_cycle
  done
}

case "${1:-run}" in
  run)
    main_loop
    ;;
  --once)
    acquire_lock
    supervisor_log "=== daily_run_supervisor --once (pid $$) ==="
    if daily_run_in_progress; then
      supervisor_log "[info] daily_run in progress; waiting for completion"
      wait_for_daily_run
    elif find_pending_poll_slot >/dev/null; then
      run_ensure_cron
      maybe_trigger_due_slots
    else
      local wait_sec
      wait_sec="$(seconds_until_next_slot_start)"
      supervisor_log "[info] no pending slot in poll window; next slot in ${wait_sec}s"
    fi
    release_lock
    trap - EXIT
    ;;
  -h|--help)
    cat <<EOF
Usage: $(basename "$0") [run|--once|-h]

Long-running loop that:
  1. Sleeps until the next Beijing slot start (07:00, 13:00, 20:00) when idle
  2. During each pending slot window, every ${POLL_SEC}s runs ensure_cron_running.sh and
     triggers daily_run.sh if data/daily_run.log has no start entry for that slot today
  3. While daily_run.sh is running, waits for completion (no further checks)

Environment:
  DAILY_RUN_SUPERVISOR_POLL_SEC       Poll interval during active slot windows (default 300)
  DAILY_RUN_SUPERVISOR_IDLE_CHUNK_SEC Max idle sleep chunk between slot recomputes (default 60)
  DAILY_RUN_TZ / DAILY_RUN_SLOT_TZ      Asia/Shanghai

Start in tmux on cron VM:
  tmux new-session -d -s daily-supervisor -c $ROOT '$ROOT/scripts/daily_run_supervisor.sh'
EOF
    ;;
  *)
    echo "[err] unknown argument: $1" >&2
    exit 1
    ;;
esac
