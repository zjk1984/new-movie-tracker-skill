#!/usr/bin/env bash
# Behavioral checks for daily_run exclusive flock (concurrent trigger prevention).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=../scripts/lib/daily_run_lock.sh
source "$ROOT/scripts/lib/daily_run_lock.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

LOCK_FILE="$TMP/daily_run.lock"
export DAILY_RUN_LOCK_FILE="$LOCK_FILE"

# First acquirer succeeds (must not use command substitution — that releases the lock).
if ! try_acquire_daily_run_lock "$LOCK_FILE" >/dev/null; then
  echo "[err] expected lock acquisition" >&2
  exit 1
fi

# Second acquirer in a subshell must fail while lock is held.
if bash -c "
  set -euo pipefail
  source '$ROOT/scripts/lib/daily_run_lock.sh'
  export DAILY_RUN_LOCK_FILE='$LOCK_FILE'
  try_acquire_daily_run_lock '$LOCK_FILE'
"; then
  echo "[err] second lock acquisition should fail" >&2
  exit 1
fi

# Lock appears held to supervisor probe.
daily_run_lock_held "$LOCK_FILE" || { echo "[err] lock should appear held" >&2; exit 1; }

# Second process must skip when the first process still holds the lock.
SKIP_OUT="$(
  bash -c "
    set -euo pipefail
    source '$ROOT/scripts/lib/daily_run_lock.sh'
    export DAILY_RUN_LOCK_FILE='$LOCK_FILE'
    if ! try_acquire_daily_run_lock '$LOCK_FILE' >/dev/null; then
      echo skip
      exit 0
    fi
    echo run
  "
)"
[[ "$SKIP_OUT" == "skip" ]] || { echo "[err] expected skip when lock held, got: $SKIP_OUT" >&2; exit 1; }

echo "[ok] daily_run lock validation passed"
