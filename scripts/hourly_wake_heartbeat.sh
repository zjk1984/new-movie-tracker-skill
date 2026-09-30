#!/usr/bin/env bash
# Hourly non-slot timer wake: ensure cron is healthy without restarting supervisor.
# Invoked on cron VM bc-d4fb1f8c when hourly-wake-non-slot-bj timer fires.
# See docs/daily-run-external-schedule.md (铁律 — hourly :55 checkpoint wake).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENSURE="$ROOT/scripts/ensure_cron_running.sh"
LOG="$ROOT/data/hourly_wake.log"

mkdir -p "$ROOT/data"

log_line() {
  printf '%s %s\n' "$(date -Is)" "$*"
}

main() {
  {
    log_line "=== hourly_wake_heartbeat start (pid $$, user $(id -un)) ==="
    if [[ -x "$ENSURE" ]]; then
      if ! "$ENSURE"; then
        log_line "[warn] ensure_cron_running exited non-zero"
      else
        log_line "[ok] ensure_cron_running completed"
      fi
    else
      log_line "[err] missing executable $ENSURE"
      exit 1
    fi
    log_line "=== hourly_wake_heartbeat done ==="
  } >>"$LOG" 2>&1
}

case "${1:-}" in
  -h|--help)
    cat <<EOF
Usage: $(basename "$0")

Lightweight hourly wake hook for non-slot Beijing :55 timer fires.
Runs ensure_cron_running.sh only (no supervisor/tmux restart).

Log: data/hourly_wake.log (also appends to data/cron_health.log via ensure_cron_running.sh)

Timer: hourly-wake-non-slot-bj (see docs/daily-run-external-schedule.md)
Cron VM: bc-d4fb1f8c
EOF
    ;;
  *)
    main "$@"
    ;;
esac
