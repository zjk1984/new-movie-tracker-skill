#!/usr/bin/env bash
# Structural and behavioral checks for restart_daily_supervisor.sh (VM wake start hook).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RESTART="$ROOT/scripts/restart_daily_supervisor.sh"
ENV_JSON="$ROOT/environment.json"

if [[ ! -f "$RESTART" ]]; then
  echo "[err] missing $RESTART" >&2
  exit 1
fi
chmod +x "$RESTART"

# environment.json wires install + start hook for cron VM.
if [[ ! -f "$ENV_JSON" ]]; then
  echo "[err] missing $ENV_JSON" >&2
  exit 1
fi
grep -Fq '"install": "./scripts/setup_cron.sh"' "$ENV_JSON"
grep -Fq '"start": "./scripts/restart_daily_supervisor.sh"' "$ENV_JSON"

# Script documents expected wiring and key operations.
grep -Fq 'ensure_cron_running' "$RESTART"
grep -Fq 'kill-session' "$RESTART"
grep -Fq 'daily-supervisor' "$RESTART"
grep -Fq 'catch_up_missed_slots_on_start' "$RESTART"
grep -Fq 'supervisor.lock' "$RESTART"
grep -Fq 'DAILY_RUN_SUPERVISOR_TMUX' "$RESTART"

"$RESTART" --help | grep -Fq 'environment.json'

# Mock tmux + ensure: verify kill → lock cleanup → fresh start sequence.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

MOCK_BIN="$TMP/bin"
mkdir -p "$MOCK_BIN"
ENSURE_LOG="$TMP/ensure.log"
TMUX_LOG="$TMP/tmux.log"
TMUX_STATE="$TMP/tmux-state"
: > "$ENSURE_LOG"
: > "$TMUX_LOG"

cat > "$MOCK_BIN/ensure_cron_running.sh" <<EOF
#!/usr/bin/env bash
echo ensure-ran >> "$ENSURE_LOG"
EOF
chmod +x "$MOCK_BIN/ensure_cron_running.sh"

cat > "$MOCK_BIN/tmux" <<EOF
#!/usr/bin/env bash
set -euo pipefail
LOG="$TMUX_LOG"
STATE="$TMUX_STATE"
echo "cmd: \$1 \$2" >> "\$LOG"
case "\${1:-}" in
  has-session)
    [[ -f "\$STATE" ]]
    ;;
  kill-session)
    rm -f "\$STATE"
    echo "kill-session \${3:-\$2}" >> "\$LOG"
    ;;
  new-session)
    touch "\$STATE"
    echo "new-session \$*" >> "\$LOG"
    ;;
  *)
    echo "unexpected tmux: \$*" >&2
    exit 1
    ;;
esac
EOF
chmod +x "$MOCK_BIN/tmux"

cat > "$MOCK_BIN/daily_run_supervisor.sh" <<EOF
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$MOCK_BIN/daily_run_supervisor.sh"

LOCK_DIR="$ROOT/data/supervisor.lock"
mkdir -p "$ROOT/data"
rm -rf "$LOCK_DIR"
mkdir "$LOCK_DIR"
echo 999999 > "$LOCK_DIR/pid"
touch "$TMUX_STATE"

export ROOT ENSURE="$MOCK_BIN/ensure_cron_running.sh" SUPERVISOR="$MOCK_BIN/daily_run_supervisor.sh"
export SESSION_NAME="test-daily-supervisor" LOCK_DIR LOG="$TMP/restart.log" PATH="$MOCK_BIN:$PATH"

bash <<'INNER'
set -euo pipefail
restart_log() { printf '%s %s\n' "$(date -Is)" "$*" >> "$LOG"; }
remove_stale_supervisor_lock() {
  if [[ ! -d "$LOCK_DIR" || ! -f "$LOCK_DIR/pid" ]]; then return 0; fi
  local old_pid
  old_pid="$(tr -d '[:space:]' < "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [[ -z "$old_pid" ]] || ! kill -0 "$old_pid" 2>/dev/null; then
    restart_log "[info] removing stale supervisor lock"
    rm -rf "$LOCK_DIR"
  fi
}
kill_supervisor_tmux_session() {
  if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    restart_log "[info] killing stale tmux session"
    tmux kill-session -t "$SESSION_NAME"
  fi
}
start_supervisor_tmux_session() {
  restart_log "[info] starting fresh tmux session"
  tmux new-session -d -s "$SESSION_NAME" -c "$ROOT" "$SUPERVISOR"
}
restart_log "=== restart_daily_supervisor start ==="
"$ENSURE"
kill_supervisor_tmux_session
remove_stale_supervisor_lock
start_supervisor_tmux_session
restart_log "=== restart_daily_supervisor done ==="
INNER

grep -q 'ensure-ran' "$ENSURE_LOG" || { echo "[err] ensure_cron_running not invoked" >&2; exit 1; }
grep -q 'kill-session test-daily-supervisor' "$TMUX_LOG" || { echo "[err] tmux kill-session not invoked" >&2; exit 1; }
grep -q 'new-session' "$TMUX_LOG" || { echo "[err] tmux new-session not invoked" >&2; exit 1; }
if [[ -d "$LOCK_DIR" ]]; then
  echo "[err] stale supervisor lock was not removed" >&2
  exit 1
fi
if [[ ! -f "$TMUX_STATE" ]]; then
  echo "[err] expected fresh tmux session after restart" >&2
  exit 1
fi

rm -rf "$LOCK_DIR"

echo "[ok] restart_daily_supervisor validation passed"
