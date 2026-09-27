#!/usr/bin/env bash
# Exclusive lock for daily_run.sh — prevents concurrent scan/download races on last_result.json.
# Sourced by daily_run.sh and daily_run_supervisor.sh; tested in tests/test_daily_run_lock.sh.
set -euo pipefail

DAILY_RUN_LOCK_FILE="${DAILY_RUN_LOCK_FILE:-}"

daily_run_lock_path() {
  local root="${1:-}"
  if [[ -z "$root" ]]; then
    echo "[err] daily_run_lock_path: root directory required" >&2
    return 2
  fi
  if [[ -n "$DAILY_RUN_LOCK_FILE" ]]; then
    printf '%s\n' "$DAILY_RUN_LOCK_FILE"
    return 0
  fi
  printf '%s/data/daily_run.lock\n' "$root"
}

# Return 0 when a daily_run.sh / daily_run.py process appears to be running.
daily_run_in_progress() {
  pgrep -f '[/ ]scripts/daily_run\.(sh|py)' >/dev/null 2>&1
}

# Try to acquire the daily_run flock (non-blocking). Echo holder pid on success.
# Return 1 when another holder has the lock or flock is unavailable.
try_acquire_daily_run_lock() {
  local lock_file="$1"
  local lock_fd=9
  mkdir -p "$(dirname "$lock_file")"
  eval "exec ${lock_fd}>\"${lock_file}\""
  if flock -n "$lock_fd"; then
    printf '%s\n' "$$"
    return 0
  fi
  return 1
}

# Return 0 when the daily_run lock file is currently held (non-blocking flock probe).
daily_run_lock_held() {
  local lock_file="$1"
  [[ -f "$lock_file" ]] || return 1
  flock -n "$lock_file" -c true 2>/dev/null && return 1
  return 0
}
