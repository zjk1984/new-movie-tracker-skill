#!/usr/bin/env bash
# Unit checks for checkpoint-safe idle sleep (chunked recompute loop).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=../scripts/lib/daily_run_slots.sh
source "$ROOT/scripts/lib/daily_run_slots.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

DAILY_RUN_SLOT_TZ=Asia/Shanghai
export DAILY_RUN_SLOT_TZ

TODAY="$(TZ="$DAILY_RUN_SLOT_TZ" date +%Y-%m-%d)"

RUN_LOG="$TMP/daily_run.log"
touch "$RUN_LOG"

IDLE_LOG=()
idle_log() {
  IDLE_LOG+=("$*")
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

SLEEP_CALLS=()
SLEEP_TOTAL=0

advance_slot_now_by() {
  local delta="$1"
  local epoch next_iso
  epoch="$(daily_run_slot_now_epoch)"
  next_iso="$(TZ="$DAILY_RUN_SLOT_TZ" date -d "@$((epoch + delta))" -Is)"
  DAILY_RUN_SLOT_NOW="$next_iso"
  export DAILY_RUN_SLOT_NOW
}

sleep() {
  SLEEP_CALLS+=("$1")
  SLEEP_TOTAL=$((SLEEP_TOTAL + 1))
  advance_slot_now_by "$1"
}

# shellcheck source=../scripts/lib/daily_run_supervisor_idle.sh
source "$ROOT/scripts/lib/daily_run_supervisor_idle.sh"

assert_eq() {
  local label="$1"
  local expected="$2"
  local got="$3"
  if [[ "$expected" == "$got" ]]; then
    return 0
  fi
  echo "[err] $label: expected '$expected', got '$got'" >&2
  return 1
}

run_idle_sleep() {
  SLEEP_CALLS=()
  SLEEP_TOTAL=0
  IDLE_LOG=()
  DAILY_RUN_SUPERVISOR_IDLE_LOG=idle_log
  export DAILY_RUN_SUPERVISOR_IDLE_LOG
  daily_run_supervisor_idle_sleep_until_next_slot
}

# 600s until 07:00 — default 60s chunks => ten sleeps
DAILY_RUN_SLOT_NOW="${TODAY}T06:50:00+08:00"
export DAILY_RUN_SLOT_NOW
unset DAILY_RUN_SUPERVISOR_IDLE_CHUNK_SEC
run_idle_sleep
assert_eq "chunk count for 600s idle" "10" "${#SLEEP_CALLS[@]}"
if ! find_pending_poll_slot >/dev/null; then
  echo "[err] expected slot 7 poll pending after idle sleep to 07:00" >&2
  exit 1
fi

# Partial final chunk: 10s remaining with 60s chunk => one sleep of 10
DAILY_RUN_SLOT_NOW="${TODAY}T06:59:50+08:00"
export DAILY_RUN_SLOT_NOW
run_idle_sleep
assert_eq "single partial chunk length" "1" "${#SLEEP_CALLS[@]}"
assert_eq "partial chunk seconds" "10" "${SLEEP_CALLS[0]}"

# Custom chunk size via env
DAILY_RUN_SLOT_NOW="${TODAY}T06:55:00+08:00"
export DAILY_RUN_SLOT_NOW
DAILY_RUN_SUPERVISOR_IDLE_CHUNK_SEC=30
export DAILY_RUN_SUPERVISOR_IDLE_CHUNK_SEC
run_idle_sleep
assert_eq "custom 30s chunk count" "10" "${#SLEEP_CALLS[@]}"
unset DAILY_RUN_SUPERVISOR_IDLE_CHUNK_SEC

# Poll window becomes active before slot start countdown finishes (07:00 slot)
DAILY_RUN_SLOT_NOW="${TODAY}T06:59:50+08:00"
export DAILY_RUN_SLOT_NOW
run_idle_sleep
assert_eq "wake on poll window" "1" "${#SLEEP_CALLS[@]}"
assert_eq "poll window chunk" "10" "${SLEEP_CALLS[0]}"
if ! find_pending_poll_slot >/dev/null; then
  echo "[err] expected slot 7 poll pending after idle sleep" >&2
  exit 1
fi

# Same pattern for 13:00 after morning slot logged
cat > "$RUN_LOG" <<EOF
===== ${TODAY}T07:05:00+08:00 daily_run.sh start (TZ=Asia/Shanghai) =====
EOF
DAILY_RUN_SLOT_NOW="${TODAY}T12:59:50+08:00"
export DAILY_RUN_SLOT_NOW
run_idle_sleep
assert_eq "wake on poll window" "1" "${#SLEEP_CALLS[@]}"
assert_eq "poll window chunk" "10" "${SLEEP_CALLS[0]}"
if ! find_pending_poll_slot >/dev/null; then
  echo "[err] expected slot 13 poll pending after idle sleep" >&2
  exit 1
fi

# At slot start with empty log — poll pending immediately, no sleep
: > "$RUN_LOG"
DAILY_RUN_SLOT_NOW="${TODAY}T07:00:00+08:00"
export DAILY_RUN_SLOT_NOW
run_idle_sleep
assert_eq "zero sleep at slot boundary" "0" "${#SLEEP_CALLS[@]}"

# Heartbeat every 15 min during long idle (mock 900s heartbeat)
DAILY_RUN_SLOT_NOW="${TODAY}T06:00:00+08:00"
export DAILY_RUN_SLOT_NOW
DAILY_RUN_SUPERVISOR_IDLE_HEARTBEAT_SEC=900
export DAILY_RUN_SUPERVISOR_IDLE_HEARTBEAT_SEC
run_idle_sleep
heartbeat_count=0
for line in "${IDLE_LOG[@]}"; do
  if [[ "$line" == *"idle heartbeat"* ]]; then
    heartbeat_count=$((heartbeat_count + 1))
  fi
done
if [[ "$heartbeat_count" -lt 1 ]]; then
  echo "[err] expected at least one idle heartbeat during 06:00-07:00 idle" >&2
  exit 1
fi
unset DAILY_RUN_SUPERVISOR_IDLE_HEARTBEAT_SEC

# Checkpoint resume simulation: one sleep overshoots into poll window (13:00)
cat > "$RUN_LOG" <<EOF
===== ${TODAY}T07:05:00+08:00 daily_run.sh start (TZ=Asia/Shanghai) =====
EOF
DAILY_RUN_SLOT_NOW="${TODAY}T12:50:00+08:00"
export DAILY_RUN_SLOT_NOW
SLEEP_CALLS=()
IDLE_LOG=()
checkpoint_sleep() {
  SLEEP_CALLS+=("$1")
  # Simulate restore jumping wall clock past 13:00 while chunk was in flight.
  DAILY_RUN_SLOT_NOW="${TODAY}T13:01:00+08:00"
  export DAILY_RUN_SLOT_NOW
}
sleep() { checkpoint_sleep "$1"; }
run_idle_sleep() {
  SLEEP_CALLS=()
  IDLE_LOG=()
  DAILY_RUN_SUPERVISOR_IDLE_LOG=idle_log
  export DAILY_RUN_SUPERVISOR_IDLE_LOG
  daily_run_supervisor_idle_sleep_until_next_slot
}
run_idle_sleep
if ! find_pending_poll_slot >/dev/null; then
  echo "[err] expected slot 13 poll pending after checkpoint resume simulation" >&2
  exit 1
fi
wake_logged=0
for line in "${IDLE_LOG[@]}"; do
  if [[ "$line" == *"after sleep chunk"* ]]; then
    wake_logged=1
    break
  fi
done
if [[ "$wake_logged" -ne 1 ]]; then
  echo "[err] expected post-chunk wake log after checkpoint resume simulation" >&2
  exit 1
fi

# Missed-slot detection for catch-up on supervisor start
: > "$RUN_LOG"
DAILY_RUN_SLOT_NOW="${TODAY}T14:00:00+08:00"
export DAILY_RUN_SLOT_NOW
missed="$(daily_run_supervisor_find_missed_slot_today "$RUN_LOG" || true)"
assert_eq "missed slot at 14:00 with empty log" "7" "$missed"

cat > "$RUN_LOG" <<EOF
===== ${TODAY}T07:05:00+08:00 daily_run.sh start (TZ=Asia/Shanghai) =====
EOF
missed="$(daily_run_supervisor_find_missed_slot_today "$RUN_LOG" || true)"
assert_eq "missed slot 13 after 7am logged" "13" "$missed"

cat > "$RUN_LOG" <<EOF
===== ${TODAY}T07:05:00+08:00 daily_run.sh start (TZ=Asia/Shanghai) =====
===== ${TODAY}T13:10:00+08:00 daily_run.sh start (TZ=Asia/Shanghai) =====
EOF
DAILY_RUN_SLOT_NOW="${TODAY}T21:00:00+08:00"
export DAILY_RUN_SLOT_NOW
missed="$(daily_run_supervisor_find_missed_slot_today "$RUN_LOG" || true)"
assert_eq "missed slot 20 after 7+13 logged" "20" "$missed"

cat > "$RUN_LOG" <<EOF
===== ${TODAY}T07:05:00+08:00 daily_run.sh start (TZ=Asia/Shanghai) =====
===== ${TODAY}T13:10:00+08:00 daily_run.sh start (TZ=Asia/Shanghai) =====
===== ${TODAY}T20:05:00+08:00 daily_run.sh start (TZ=Asia/Shanghai) =====
EOF
if daily_run_supervisor_find_missed_slot_today "$RUN_LOG" >/dev/null; then
  echo "[err] expected no missed slots when all ran today" >&2
  exit 1
fi

DAILY_RUN_SLOT_NOW="${TODAY}T06:30:00+08:00"
export DAILY_RUN_SLOT_NOW
if daily_run_supervisor_find_missed_slot_today "$RUN_LOG" >/dev/null; then
  echo "[err] expected no missed slots before 07:00 start" >&2
  exit 1
fi

# Supervisor wires chunked idle helper + catch-up
SUP="$ROOT/scripts/daily_run_supervisor.sh"
[[ -x "$SUP" ]] || chmod +x "$SUP"
grep -Fq 'daily_run_supervisor_idle_sleep_until_next_slot' "$SUP"
grep -Fq 'DAILY_RUN_SUPERVISOR_IDLE_CHUNK_SEC' "$SUP"
grep -Fq 'DAILY_RUN_SUPERVISOR_IDLE_HEARTBEAT_SEC' "$SUP"
grep -Fq 'daily_run_supervisor_find_missed_slot_today' "$SUP"
grep -Fq 'catch_up_missed_slots_on_start' "$SUP"
grep -Fq 'daily_run_supervisor_idle.sh' "$SUP"

echo "[ok] daily_run_supervisor idle sleep passed"
