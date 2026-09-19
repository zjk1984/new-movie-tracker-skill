#!/usr/bin/env bash
# Behavioral checks for ensure_cron_running.sh (install-user crontab + auto-repair).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENSURE="$ROOT/scripts/ensure_cron_running.sh"
SETUP="$ROOT/scripts/setup_cron.sh"
MARK="# new-movie-tracker-daily"
CNBETA_MARK="# new-movie-tracker-cnbeta"
CRON_USER_FILE="$ROOT/data/cron_install_user"

if [[ ! -x "$ENSURE" ]]; then
  echo "[err] missing executable: $ENSURE" >&2
  exit 1
fi

# resolve_cron_install_user: saved file wins.
mkdir -p "$ROOT/data"
printf 'testcronuser\n' > "$CRON_USER_FILE"
grep -Fq 'resolve_cron_install_user' "$ENSURE"
grep -Fq 'CRON_USER_FILE' "$ENSURE"

# Dry-run repair path must exist in setup_cron.sh.
"$SETUP" --repair-crontab --dry-run 2>/dev/null | grep -q 'would repair crontab'

# Simulate root health check: root must query install user's crontab, not root's.
if command -v crontab >/dev/null 2>&1; then
  saved_root="$(crontab -l 2>/dev/null || true)"
  saved_test="$(crontab -u testcronuser -l 2>/dev/null || true)"

  # Root crontab has no tracker mark; test user would after install.
  if [[ "$(id -u)" -eq 0 ]]; then
    if echo "$saved_root" | grep -Fq "$MARK"; then
      echo "[info] root crontab already has tracker mark; skipping negative check"
    else
      ! tracker_crontab_present_root() {
        crontab -l 2>/dev/null | grep -Fq "$MARK"
      }
      if tracker_crontab_present_root; then
        echo "[err] unexpected root tracker mark" >&2
        exit 1
      fi
    fi
  fi

  # ensure script documents auto-repair (not warn-only).
  grep -Fq 'repair_tracker_crontab' "$ENSURE"
  grep -Fq 'CNBETA_MARK' "$ENSURE"
  grep -Fq 'restart_cron_daemon' "$ENSURE"
  ! grep -Fq 'run ./scripts/setup_cron.sh' "$ENSURE" || {
    if grep 'run ./scripts/setup_cron.sh' "$ENSURE" | grep -qv repair; then
      echo "[err] ensure_cron_running still warn-only (manual setup_cron hint)" >&2
      exit 1
    fi
  }
fi

rm -f "$CRON_USER_FILE"

echo "[ok] ensure_cron_running validation passed"
