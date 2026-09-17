#!/usr/bin/env bash
# Root @reboot hook: wait for boot, restart cron, log outcome.
# Installed via /etc/cron.d/new-movie-tracker-reboot by scripts/setup_cron.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/data/cron_reboot.log"
PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

mkdir -p "$ROOT/data"

{
  echo "=== $(date -Is) cron reboot reload start (pid $$) ==="
  sleep 30

  if command -v service >/dev/null 2>&1 && service cron restart 2>/dev/null; then
    echo "[ok] service cron restart"
  elif command -v systemctl >/dev/null 2>&1 && systemctl restart cron 2>/dev/null; then
    echo "[ok] systemctl restart cron"
  elif command -v service >/dev/null 2>&1 && service crond restart 2>/dev/null; then
    echo "[ok] service crond restart"
  elif command -v systemctl >/dev/null 2>&1 && systemctl restart crond 2>/dev/null; then
    echo "[ok] systemctl restart crond"
  else
    echo "[err] could not restart cron/crond"
    exit 1
  fi

  echo "=== $(date -Is) cron reboot reload done ==="
} >>"$LOG" 2>&1
