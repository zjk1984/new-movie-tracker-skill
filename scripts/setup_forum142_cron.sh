#!/usr/bin/env bash
# Install forum-142 batch scan cron (daily 14:00 Asia/Shanghai by default).
# Usage: ./scripts/setup_forum142_cron.sh [--dry-run] [--repair-crontab] [--remove]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WRAPPER="$ROOT/scripts/forum142_batch_run.sh"
MARK="# new-movie-tracker-forum142-batch"
CRON_USER_FILE="$ROOT/data/cron_install_user"
TZ_NAME="${FORUM142_CRON_TZ:-Asia/Shanghai}"
WEEKDAYS="${FORUM142_CRON_WEEKDAYS:-*}"
TIME="${FORUM142_CRON_TIME:-14:00}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --repair-crontab)
      REPAIR_CRONTAB=1
      shift
      ;;
    --remove)
      REMOVE=1
      shift
      ;;
    -h|--help)
      cat <<EOF
Install cron job for scripts/forum142_batch_run.sh (forum-142 custom batch scan).

Default schedule: daily 14:00 Asia/Shanghai (Beijing time).
Requires system timezone Asia/Shanghai (Vixie cron uses system local time).
After install, attempts to restart the cron daemon automatically.

Does not modify daily_run or forum37 batch slots installed by other setup scripts.

Usage:
  ./scripts/setup_forum142_cron.sh [--dry-run] [--repair-crontab] [--remove]

Environment overrides:
  FORUM142_CRON_TZ=Asia/Shanghai
  FORUM142_CRON_TIME=14:00
  FORUM142_CRON_WEEKDAYS=*        cron DOW (0=Sun … 6=Sat; * = every day; default daily)

Deploy on cron VM bc-d4fb1f8c after merge:
  cd /workspace && git pull origin main
  ./scripts/setup_forum142_cron.sh
  crontab -l | grep forum142
EOF
      exit 0
      ;;
    *)
      echo "[err] unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

resolve_cron_install_user() {
  if [[ -f "$CRON_USER_FILE" ]]; then
    tr -d '[:space:]' < "$CRON_USER_FILE"
    return 0
  fi
  if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != root ]]; then
    echo "$SUDO_USER"
    return 0
  fi
  if [[ "$(id -u)" -ne 0 ]]; then
    id -un
    return 0
  fi
  echo "${CRON_INSTALL_USER:-ubuntu}"
}

save_cron_install_user() {
  local user="$1"
  mkdir -p "$ROOT/data"
  printf '%s\n' "$user" > "$CRON_USER_FILE"
}

cron_line_for_forum142() {
  local time="$1"
  if ! [[ "$time" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]]; then
    echo "[err] invalid time '$time' (expected HH:MM, 24h)" >&2
    return 1
  fi
  local hour="${time%%:*}"
  local minute="${time#*:}"
  hour="${hour#0}"
  hour="${hour:-0}"
  minute="${minute#0}"
  minute="${minute:-0}"
  echo "$minute $hour * * $WEEKDAYS TZ=$TZ_NAME $WRAPPER $MARK"
}

is_forum142_cron_line() {
  local line="$1"
  [[ "$line" == *"$WRAPPER"* ]] || [[ "$line" == *"$MARK"* ]]
}

restart_cron_daemon() {
  if sudo -n service cron restart 2>/dev/null; then
    echo "[ok] cron daemon restarted (sudo service cron restart)"
    return 0
  fi
  if sudo -n systemctl restart cron 2>/dev/null; then
    echo "[ok] cron daemon restarted (sudo systemctl restart cron)"
    return 0
  fi
  if service cron restart 2>/dev/null; then
    echo "[ok] cron daemon restarted (service cron restart)"
    return 0
  fi
  echo "[warn] could not restart cron daemon automatically; run manually: sudo service cron restart" >&2
  return 1
}

install_user_crontab_line() {
  local install_user="$1"
  local new_line="$2"
  local remove_only="${3:-0}"

  if ! command -v crontab >/dev/null 2>&1; then
    echo "[err] crontab not installed. Install cron (e.g. apt install cron) first." >&2
    return 1
  fi

  save_cron_install_user "$install_user"

  local tmp
  tmp="$(mktemp)"
  local crontab_cmd=(crontab)
  if [[ "$(id -un)" != "$install_user" ]]; then
    if [[ "$(id -u)" -eq 0 ]]; then
      crontab_cmd=(crontab -u "$install_user")
    else
      rm -f "$tmp"
      echo "[err] cannot install crontab for $install_user (run as $install_user or root)" >&2
      return 1
    fi
  fi

  while IFS= read -r line || [[ -n "$line" ]]; do
    if is_forum142_cron_line "$line"; then
      continue
    fi
    printf '%s\n' "$line"
  done < <("${crontab_cmd[@]}" -l 2>/dev/null || true) > "$tmp"

  if [[ "$remove_only" -eq 0 ]]; then
    echo "$new_line" >> "$tmp"
  fi

  "${crontab_cmd[@]}" "$tmp"
  rm -f "$tmp"
}

line="$(cron_line_for_forum142 "$TIME")"

if [[ "${REMOVE:-0}" == 1 ]]; then
  install_user="$(resolve_cron_install_user)"
  if [[ "${DRY_RUN:-0}" == 1 ]]; then
    echo "[dry-run] would remove forum142 cron line for $install_user"
    exit 0
  fi
  install_user_crontab_line "$install_user" "" 1
  echo "[ok] forum142 cron removed for $install_user"
  restart_cron_daemon || true
  exit 0
fi

if [[ "${DRY_RUN:-0}" == 1 ]]; then
  echo "[dry-run] would install forum142 cron line:"
  echo "  $line"
  echo "  log: $ROOT/data/forum142_batch_run.log"
  echo "  reports: $ROOT/reports/forum-142_YYYY-MM-DD.md"
  exit 0
fi

chmod +x "$WRAPPER"
mkdir -p "$ROOT/data" "$ROOT/reports"

install_user="$(resolve_cron_install_user)"
if ! install_user_crontab_line "$install_user" "$line" 0; then
  exit 1
fi

echo "[ok] forum142 cron installed for $install_user:"
echo "     $line"
echo "     timezone: $TZ_NAME (system TZ should match for correct schedule)"
echo "     schedule: daily at $TIME (weekdays field: $WEEKDAYS)"
echo "     log: $ROOT/data/forum142_batch_run.log"
echo "     reports: $ROOT/reports/forum-142_YYYY-MM-DD.md"
crontab -l 2>/dev/null | grep -E 'new-movie-tracker-forum142|forum142_batch_run' || true

restart_cron_daemon || true
