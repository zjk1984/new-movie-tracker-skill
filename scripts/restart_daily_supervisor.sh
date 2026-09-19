#!/usr/bin/env bash
# VM start/wake hook: ensure cron is healthy and restart daily_run_supervisor in tmux
# so catch_up_missed_slots_on_start re-evaluates missed Beijing slots after checkpoint
# restore (the frozen supervisor process cannot recover on its own).
#
# Intended for Cloud Agent environment.json "start" (alongside setup_cron.sh in install).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENSURE="$ROOT/scripts/ensure_cron_running.sh"
SUPERVISOR="$ROOT/scripts/daily_run_supervisor.sh"
SESSION_NAME="${DAILY_RUN_SUPERVISOR_TMUX:-daily-supervisor}"
LOCK_DIR="$ROOT/data/supervisor.lock"
LOG="$ROOT/data/supervisor_restart.log"

mkdir -p "$ROOT/data"

restart_log() {
  printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$LOG"
}

remove_stale_supervisor_lock() {
  if [[ ! -d "$LOCK_DIR" || ! -f "$LOCK_DIR/pid" ]]; then
    return 0
  fi
  local old_pid
  old_pid="$(tr -d '[:space:]' < "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [[ -z "$old_pid" ]] || ! kill -0 "$old_pid" 2>/dev/null; then
    restart_log "[info] removing stale supervisor lock (pid ${old_pid:-unknown} not running)"
    rm -rf "$LOCK_DIR"
  fi
}

kill_supervisor_tmux_session() {
  if ! command -v tmux >/dev/null 2>&1; then
    restart_log "[warn] tmux not available; cannot manage supervisor session"
    return 1
  fi
  if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    restart_log "[info] killing stale tmux session $SESSION_NAME"
    tmux kill-session -t "$SESSION_NAME" || true
  fi
  return 0
}

start_supervisor_tmux_session() {
  if ! command -v tmux >/dev/null 2>&1; then
    restart_log "[err] tmux not available; cannot start supervisor"
    return 1
  fi
  if [[ ! -x "$SUPERVISOR" ]]; then
    chmod +x "$SUPERVISOR"
  fi
  restart_log "[info] starting fresh tmux session $SESSION_NAME"
  tmux new-session -d -s "$SESSION_NAME" -c "$ROOT" "$SUPERVISOR"
  return 0
}

main() {
  restart_log "=== restart_daily_supervisor start (pid $$, session=$SESSION_NAME) ==="

  if [[ -x "$ENSURE" ]]; then
    if ! "$ENSURE"; then
      restart_log "[warn] ensure_cron_running exited non-zero"
    fi
  else
    restart_log "[warn] missing $ENSURE"
  fi

  kill_supervisor_tmux_session || true
  remove_stale_supervisor_lock

  if ! start_supervisor_tmux_session; then
    restart_log "=== restart_daily_supervisor failed (no tmux) ==="
    exit 1
  fi

  restart_log "=== restart_daily_supervisor done ==="
}

case "${1:-}" in
  -h|--help)
    cat <<EOF
Usage: $(basename "$0")

Ensures cron health, kills stale daily-supervisor tmux session, and starts a fresh
daily_run_supervisor.sh so missed Beijing slots are caught up on VM wake.

Environment:
  DAILY_RUN_SUPERVISOR_TMUX   tmux session name (default: daily-supervisor)

Cloud Agent environment.json:
  "install": "./scripts/setup_cron.sh",
  "start": "./scripts/restart_daily_supervisor.sh"
EOF
    ;;
  *)
    main "$@"
    ;;
esac
