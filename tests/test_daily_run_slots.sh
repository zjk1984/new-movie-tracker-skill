#!/usr/bin/env bash
# Unit checks for daily_run slot detection (07/13/20 Beijing windows).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=../scripts/lib/daily_run_slots.sh
source "$ROOT/scripts/lib/daily_run_slots.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

write_log() {
  cat > "$TMP/daily_run.log"
}

assert_slot_ran() {
  local slot="$1"
  local today="$2"
  if daily_run_slot_ran_today "$slot" "$TMP/daily_run.log" "$today"; then
    return 0
  fi
  echo "[err] expected slot $slot to be marked ran on $today" >&2
  return 1
}

assert_slot_not_ran() {
  local slot="$1"
  local today="$2"
  if daily_run_slot_ran_today "$slot" "$TMP/daily_run.log" "$today"; then
    echo "[err] expected slot $slot NOT ran on $today" >&2
    return 1
  fi
}

TODAY="2026-09-18"

# 07:00 slot — morning window
write_log <<EOF
===== 2026-09-18T07:00:12+08:00 daily_run.sh start (TZ=Asia/Shanghai) =====
===== 2026-09-18T07:45:00+08:00 daily_run.sh exit 0 =====
EOF
assert_slot_ran 7 "$TODAY"
assert_slot_not_ran 13 "$TODAY"
assert_slot_not_ran 20 "$TODAY"

# 13:00 slot — afternoon window
write_log <<EOF
===== 2026-09-18T13:02:01+08:00 daily_run.sh start (TZ=Asia/Shanghai) =====
EOF
assert_slot_not_ran 7 "$TODAY"
assert_slot_ran 13 "$TODAY"
assert_slot_not_ran 20 "$TODAY"

# 20:00 slot — evening + late catch-up (21:43)
write_log <<EOF
===== 2026-09-18T21:43:24+08:00 daily_run.sh start (TZ=Asia/Shanghai) =====
EOF
assert_slot_ran 20 "$TODAY"
assert_slot_not_ran 7 "$TODAY"
assert_slot_not_ran 13 "$TODAY"

# Wrong day — should not count for today
write_log <<EOF
===== 2026-09-17T20:30:00+08:00 daily_run.sh start (TZ=Asia/Shanghai) =====
EOF
assert_slot_not_ran 20 "$TODAY"

# Hour boundaries: 12:59 counts as 07 slot; 19:59 as 13 slot; 06:59 does not count
write_log <<EOF
===== 2026-09-18T06:59:00+08:00 daily_run.sh start (TZ=Asia/Shanghai) =====
===== 2026-09-18T12:59:59+08:00 daily_run.sh start (TZ=Asia/Shanghai) =====
EOF
assert_slot_ran 7 "$TODAY"
assert_slot_not_ran 13 "$TODAY"

write_log <<EOF
===== 2026-09-18T19:59:00+08:00 daily_run.sh start (TZ=Asia/Shanghai) =====
EOF
assert_slot_ran 13 "$TODAY"
assert_slot_not_ran 20 "$TODAY"

# Missing log file
rm -f "$TMP/daily_run.log"
assert_slot_not_ran 7 "$TODAY"

# Window helpers
DAILY_RUN_SLOT_TZ=Asia/Shanghai
export DAILY_RUN_SLOT_TZ
if daily_run_slot_hour_in_window 7 12; then :; else
  echo "[err] hour 12 should be in slot 7 window" >&2
  exit 1
fi
if daily_run_slot_hour_in_window 7 13; then
  echo "[err] hour 13 should not be in slot 7 window" >&2
  exit 1
fi
if daily_run_slot_hour_in_window 20 21; then :; else
  echo "[err] hour 21 should be in slot 20 window" >&2
  exit 1
fi

# Poll window: active from slot start until next slot start
assert_poll_active() {
  local slot="$1"
  local now="$2"
  DAILY_RUN_SLOT_NOW="$now"
  export DAILY_RUN_SLOT_NOW
  if daily_run_slot_poll_active "$slot"; then
    return 0
  fi
  echo "[err] expected slot $slot poll active at $now" >&2
  return 1
}

assert_poll_inactive() {
  local slot="$1"
  local now="$2"
  DAILY_RUN_SLOT_NOW="$now"
  export DAILY_RUN_SLOT_NOW
  if daily_run_slot_poll_active "$slot"; then
    echo "[err] expected slot $slot poll inactive at $now" >&2
    return 1
  fi
}

assert_seconds_until() {
  local now="$1"
  local expected="$2"
  local got
  DAILY_RUN_SLOT_NOW="$now"
  export DAILY_RUN_SLOT_NOW
  got="$(seconds_until_next_slot_start)"
  if [[ "$got" -eq "$expected" ]]; then
    return 0
  fi
  echo "[err] at $now expected ${expected}s until next slot, got ${got}s" >&2
  return 1
}

assert_poll_active 7 "2026-09-18T07:00:00+08:00"
assert_poll_active 7 "2026-09-18T12:59:00+08:00"
assert_poll_inactive 7 "2026-09-18T06:50:00+08:00"
assert_poll_inactive 7 "2026-09-18T13:00:00+08:00"

assert_poll_active 13 "2026-09-18T13:00:00+08:00"
assert_poll_inactive 13 "2026-09-18T12:00:00+08:00"

assert_poll_active 20 "2026-09-18T20:00:00+08:00"
assert_poll_inactive 20 "2026-09-18T19:59:00+08:00"

assert_seconds_until "2026-09-18T06:50:00+08:00" 600
assert_seconds_until "2026-09-18T12:00:00+08:00" 3600
assert_seconds_until "2026-09-18T21:00:00+08:00" 36000

# Pending-for-poll combines log state + poll window
write_log <<EOF
===== 2026-09-18T07:05:00+08:00 daily_run.sh start (TZ=Asia/Shanghai) =====
EOF
DAILY_RUN_SLOT_NOW="2026-09-18T08:00:00+08:00"
export DAILY_RUN_SLOT_NOW
if daily_run_slot_pending_for_poll 7 "$TMP/daily_run.log"; then
  echo "[err] slot 7 should not be pending after morning run logged" >&2
  exit 1
fi
if daily_run_slot_pending_for_poll 13 "$TMP/daily_run.log"; then
  echo "[err] slot 13 should not be pending at 08:00 (before 13:00 poll window)" >&2
  exit 1
fi

DAILY_RUN_SLOT_NOW="2026-09-18T14:00:00+08:00"
export DAILY_RUN_SLOT_NOW
if ! daily_run_slot_pending_for_poll 13 "$TMP/daily_run.log"; then
  echo "[err] slot 13 should be pending at 14:00 before its log entry" >&2
  exit 1
fi

unset DAILY_RUN_SLOT_NOW

# Supervisor script exists and documents tmux + slot-based sleep
SUP="$ROOT/scripts/daily_run_supervisor.sh"
[[ -x "$SUP" ]] || chmod +x "$SUP"
grep -Fq 'daily_run_slot_ran_today' "$SUP"
grep -Fq 'seconds_until_next_slot_start' "$SUP"
grep -Fq 'daily_run_supervisor_idle_sleep_until_next_slot' "$SUP"
grep -Fq 'DAILY_RUN_SUPERVISOR_IDLE_CHUNK_SEC' "$SUP"
grep -Fq 'ensure_cron_running' "$SUP"
grep -Fq 'tmux' "$SUP"

echo "[ok] daily_run slot detection passed"
