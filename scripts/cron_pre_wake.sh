#!/usr/bin/env bash
# Five-minute pre-wake before tracker user crontab jobs (VM checkpoint / sleep).
# Delegates to existing hooks — no duplicate supervisor/cron logic.
#
# Usage:
#   cron_pre_wake.sh dedupe          # before GuangYa/PikPak dedupe slot (default 06:45 BJ)
#   cron_pre_wake.sh daily <7|13|20> # before daily_run.sh Beijing slot
#
# Log: data/cron_pre_wake.log (ensure_cron also appends to data/cron_health.log)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENSURE="$ROOT/scripts/ensure_cron_running.sh"
RESTART_SUP="$ROOT/scripts/restart_daily_supervisor.sh"
LOG="$ROOT/data/cron_pre_wake.log"
TZ_NAME="${DAILY_RUN_TZ:-Asia/Shanghai}"

mkdir -p "$ROOT/data"

log_line() {
  printf '%s %s\n' "$(TZ="$TZ_NAME" date -Is)" "$*"
}

run_logged() {
  {
    log_line "$@"
    "$2"
    log_line "=== cron_pre_wake done ($1) ==="
  } >>"$LOG" 2>&1
}

usage() {
  cat <<EOF
Usage: $(basename "$0") dedupe
       $(basename "$0") daily <7|13|20>

Runs 5 minutes before matching setup_cron.sh jobs (Asia/Shanghai).
  dedupe     — ensure_cron_running.sh (dedupe is cron-only)
  daily N    — restart_daily_supervisor.sh (missed-slot catch-up)

Log: data/cron_pre_wake.log
EOF
}

main() {
  local kind="${1:-}"
  case "$kind" in
    dedupe)
      if [[ ! -x "$ENSURE" ]]; then
        log_line "[err] missing $ENSURE" >>"$LOG"
        exit 1
      fi
      run_logged "dedupe" "$ENSURE"
      ;;
    daily)
      local slot="${2:-}"
      case "$slot" in
        7|13|20) ;;
        *)
          echo "[err] daily pre-wake requires slot 7, 13, or 20 (got ${slot:-empty})" >&2
          exit 1
          ;;
      esac
      if [[ ! -x "$RESTART_SUP" ]]; then
        log_line "[err] missing $RESTART_SUP" >>"$LOG"
        exit 1
      fi
      run_logged "daily-${slot}" "$RESTART_SUP"
      ;;
    -h|--help)
      usage
      ;;
    *)
      usage >&2
      exit 1
      ;;
  esac
}

main "$@"
