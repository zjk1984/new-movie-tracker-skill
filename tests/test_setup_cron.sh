#!/usr/bin/env bash
# shellcheck disable=SC2034
# Validation for scripts/setup_cron.sh (cron install + daemon reload + health watchdog).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/scripts/setup_cron.sh"
REBOOT_SCRIPT="$ROOT/scripts/cron_reboot_reload.sh"
ENSURE_SCRIPT="$ROOT/scripts/ensure_cron_running.sh"

if [[ ! -x "$SCRIPT" ]]; then
  echo "[err] missing executable: $SCRIPT" >&2
  exit 1
fi

if [[ ! -x "$REBOOT_SCRIPT" ]]; then
  echo "[err] missing executable: $REBOOT_SCRIPT" >&2
  exit 1
fi

if [[ ! -x "$ENSURE_SCRIPT" ]]; then
  echo "[err] missing executable: $ENSURE_SCRIPT" >&2
  exit 1
fi

DRY="$("$SCRIPT" --dry-run 2>/dev/null)"
echo "$DRY" | grep -q 'would install cron line(s):'
echo "$DRY" | grep -q 'new-movie-tracker-daily'
echo "$DRY" | grep -q '/etc/cron.d/new-movie-tracker-reboot'
echo "$DRY" | grep -q '/etc/cron.d/new-movie-tracker-health'
echo "$DRY" | grep -q 'cron_reboot_reload.sh'
echo "$DRY" | grep -q 'ensure_cron_running.sh\|--ensure-only\|health watchdog'
"$SCRIPT" --help | grep -qi 'restart'
"$SCRIPT" --help | grep -qi 'cron.d'
"$SCRIPT" --help | grep -qi 'starts at boot\|enabled at boot'
"$SCRIPT" --help | grep -qi 'ensure-only'
"$SCRIPT" --help | grep -qi 'tini\|container'

ENSURE_DRY="$("$SCRIPT" --ensure-only --dry-run 2>/dev/null)"
echo "$ENSURE_DRY" | grep -q 'would run:.*ensure_cron_running.sh'
echo "$ENSURE_DRY" | grep -q 'new-movie-tracker-health'

# User crontab must NOT use sudo @reboot (fails under cron: no TTY, minimal PATH).
if echo "$DRY" | grep -q '@reboot.*sudo'; then
  echo "[err] user crontab still installs sudo @reboot" >&2
  exit 1
fi

# Reboot hook script must not depend on sudo.
grep -Fq 'sudo' "$REBOOT_SCRIPT" && {
  echo "[err] cron_reboot_reload.sh must not use sudo" >&2
  exit 1
}

# Restart attempts must appear in priority order in setup_cron.sh.
grep -Fq 'if sudo -n service cron restart' "$SCRIPT"
grep -Fq 'if sudo -n systemctl restart cron' "$SCRIPT"
grep -Fq 'if service cron restart' "$SCRIPT"

awk '
  /if sudo -n service cron restart/ { a=1 }
  /if sudo -n systemctl restart cron/ { if (!a) exit 1; b=1 }
  /if service cron restart/ { if (!b) exit 1; c=1 }
  END { exit !(a && b && c) }
' "$SCRIPT"

grep -Fq 'systemctl is-enabled' "$SCRIPT"
grep -Fq 'systemctl enable --now' "$SCRIPT"
grep -Fq 'install_reboot_cron_d' "$SCRIPT"
grep -Fq 'install_health_cron_d' "$SCRIPT"
grep -Fq 'ensure_cron_running.sh' "$SCRIPT"
grep -Fq 'new-movie-tracker-cron-ensure' "$SCRIPT"
grep -Fq 'cron_health.log' "$ENSURE_SCRIPT"

echo "[ok] setup_cron validation passed"
