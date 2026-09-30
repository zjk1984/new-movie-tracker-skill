#!/usr/bin/env bash
# Structural and behavioral checks for hourly_wake_heartbeat.sh (non-slot timer wake).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HEARTBEAT="$ROOT/scripts/hourly_wake_heartbeat.sh"

if [[ ! -f "$HEARTBEAT" ]]; then
  echo "[err] missing $HEARTBEAT" >&2
  exit 1
fi
chmod +x "$HEARTBEAT"

grep -Fq 'ensure_cron_running' "$HEARTBEAT"
grep -Fq 'hourly_wake.log' "$HEARTBEAT"
grep -Fq 'hourly-wake-non-slot-bj' "$HEARTBEAT"
! grep -Fq 'restart_daily_supervisor' "$HEARTBEAT"
! grep -Fq 'kill-session' "$HEARTBEAT"
! grep -Fq 'tmux' "$HEARTBEAT"

"$HEARTBEAT" --help | grep -Fq 'ensure_cron_running.sh only'

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/scripts" "$TMP/data"
ENSURE_LOG="$TMP/ensure.log"
: > "$ENSURE_LOG"

cp "$HEARTBEAT" "$TMP/scripts/hourly_wake_heartbeat.sh"
chmod +x "$TMP/scripts/hourly_wake_heartbeat.sh"

cat > "$TMP/scripts/ensure_cron_running.sh" <<EOF
#!/usr/bin/env bash
echo ensure-ran >> "$ENSURE_LOG"
EOF
chmod +x "$TMP/scripts/ensure_cron_running.sh"

"$TMP/scripts/hourly_wake_heartbeat.sh"

grep -q 'ensure-ran' "$ENSURE_LOG"
grep -Fq 'hourly_wake_heartbeat start' "$TMP/data/hourly_wake.log"
grep -Fq 'hourly_wake_heartbeat done' "$TMP/data/hourly_wake.log"

echo "[ok] hourly_wake_heartbeat validation passed"
