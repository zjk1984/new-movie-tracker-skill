#!/usr/bin/env bash
# Install daily_run cron jobs (07:00 + 13:00 + 20:00 Asia/Shanghai by default).
# Usage: ./scripts/setup_cron.sh [--dry-run] [--ensure-only] [--time HH:MM] [--time HH:MM ...]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WRAPPER="$ROOT/scripts/daily_run.sh"
REBOOT_SCRIPT="$ROOT/scripts/cron_reboot_reload.sh"
ENSURE_SCRIPT="$ROOT/scripts/ensure_cron_running.sh"
MARK="# new-movie-tracker-daily"
REBOOT_MARK="# new-movie-tracker-daily-reboot"
REBOOT_CRON_D="/etc/cron.d/new-movie-tracker-reboot"
HEALTH_CRON_D="/etc/cron.d/new-movie-tracker-health"
CRON_ENSURE_UNIT="new-movie-tracker-cron-ensure"
CRON_ENSURE_SERVICE="/etc/systemd/system/${CRON_ENSURE_UNIT}.service"
CRON_USER_FILE="$ROOT/data/cron_install_user"
TZ_NAME="${DAILY_RUN_TZ:-Asia/Shanghai}"
TIMES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --ensure-only)
      ENSURE_ONLY=1
      shift
      ;;
    --repair-crontab)
      REPAIR_CRONTAB=1
      shift
      ;;
    --time)
      TIMES+=("${2:?missing value for --time}")
      shift 2
      ;;
    -h|--help)
      cat <<EOF
Install cron job(s) for scripts/daily_run.sh.

Default schedule: 07:00, 13:00, and 20:00 Asia/Shanghai (Beijing time).
Requires system timezone Asia/Shanghai (Vixie cron uses system local time).
After install, attempts to restart the cron daemon automatically (required on some VMs).
Also installs root /etc/cron.d hooks:
  - @reboot reload (when cron starts)
  - health watchdog (ensure daemon + install-user crontab; every 15 min 06:00–21:59 Beijing)
Ensures cron starts at boot via systemctl/service and optional systemd oneshot unit.
Use --ensure-only for idempotent health checks (auto-fixes missing crontab / stopped cron).
Use --repair-crontab to reinstall daily slots for the install user only (internal / watchdog).

Usage:
  ./scripts/setup_cron.sh [--dry-run] [--ensure-only] [--time HH:MM] [--time HH:MM ...]

  Repeat --time to override defaults, e.g.:
    ./scripts/setup_cron.sh --time 07:00 --time 13:00 --time 20:00

Environment overrides:
  DAILY_RUN_TZ=Asia/Shanghai
  DAILY_RUN_TIMES=07:00,13:00,20:00

Container / Cloud Agent VMs (PID 1 is tini, cron may start late or die):
  Cron is best-effort. Run the external supervisor in tmux (recommended):
    tmux new-session -d -s daily-supervisor -c $ROOT '$ROOT/scripts/daily_run_supervisor.sh'
  Optionally add environment.json "start": "./scripts/ensure_cron_running.sh"
  @reboot only fires when cron finally starts — it cannot fix a missed 07:00 slot.
EOF
      exit 0
      ;;
    *)
      echo "[err] unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ${#TIMES[@]} -eq 0 ]]; then
  # shellcheck disable=SC2206
  TIMES=(${DAILY_RUN_TIMES:-07:00,13:00,20:00})
fi

# Normalize comma-separated env values and dedupe while preserving order.
normalize_times() {
  local raw joined="" time seen="|"
  for raw in "${TIMES[@]}"; do
    joined="${joined},${raw}"
  done
  joined="${joined#,}"
  joined="${joined//,/ }"
  TIMES=()
  for time in $joined; do
    time="${time// /}"
    [[ -z "$time" ]] && continue
    if [[ "$seen" != *"|$time|"* ]]; then
      TIMES+=("$time")
      seen="${seen}${time}|"
    fi
  done
}

normalize_times

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

cron_line_for_time() {
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
  echo "$minute $hour * * * TZ=$TZ_NAME $WRAPPER $MARK"
}

is_tracker_cron_line() {
  local line="$1"
  [[ "$line" == *"$WRAPPER"* ]] || [[ "$line" == *"$MARK"* ]] || [[ "$line" == *"$REBOOT_MARK"* ]] || [[ "$line" == *"@reboot"* && "$line" == *"new-movie-tracker"* ]]
}

cron_service_unit() {
  if systemctl list-unit-files cron.service >/dev/null 2>&1; then
    echo cron
  elif systemctl list-unit-files crond.service >/dev/null 2>&1; then
    echo crond
  else
    echo ""
  fi
}

ensure_cron_boot_enabled() {
  if ! command -v systemctl >/dev/null 2>&1; then
    echo "[info] systemctl not available; run ensure_cron_running.sh from your container start hook"
    return 0
  fi

  local unit
  unit="$(cron_service_unit)"
  if [[ -z "$unit" ]]; then
    echo "[warn] cron systemd unit not found; install cron package (e.g. apt install cron)" >&2
    return 1
  fi

  local state
  state="$(systemctl is-enabled "$unit" 2>/dev/null || echo unknown)"
  case "$state" in
    enabled|static|alias)
      echo "[ok] $unit service enabled at boot ($state)"
      return 0
      ;;
    masked)
      echo "[warn] $unit service is masked; unmask and enable: sudo systemctl unmask $unit && sudo systemctl enable $unit" >&2
      return 1
      ;;
    disabled|disabled-by-failure|generated|indirect|not-found|unknown)
      echo "[warn] $unit service not enabled at boot (is-enabled: $state)" >&2
      if [[ "${DRY_RUN:-0}" == 1 ]]; then
        echo "[dry-run] would run: sudo systemctl enable --now $unit"
        return 0
      fi
      if sudo -n systemctl enable --now "$unit" 2>/dev/null; then
        echo "[ok] enabled and started $unit at boot"
        return 0
      fi
      if sudo -n systemctl enable "$unit" 2>/dev/null; then
        echo "[ok] enabled $unit service at boot"
        return 0
      fi
      echo "[warn] run manually: sudo systemctl enable --now $unit" >&2
      return 1
      ;;
    *)
      echo "[warn] unexpected is-enabled state for $unit: $state" >&2
      return 1
      ;;
  esac
}

reboot_cron_d_content() {
  cat <<EOF
# Installed by scripts/setup_cron.sh — reload cron when the daemon starts (@reboot).
# On container VMs cron may start hours after VM boot; use ensure_cron_running.sh at start.
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
@reboot root $REBOOT_SCRIPT
EOF
}

health_cron_d_content() {
  local user
  user="$(resolve_cron_install_user)"
  cat <<EOF
# Installed by scripts/setup_cron.sh — watchdog while cron is running.
# Runs as the install user ($user) so crontab checks target the correct account.
# Requires system timezone Asia/Shanghai for 06:00–21:59 active window.
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
*/15 6-21 * * * $user $ENSURE_SCRIPT
0,30 0-5,22-23 * * * $user $ENSURE_SCRIPT
EOF
}

install_cron_d_file() {
  local dest="$1"
  local content="$2"
  local label="$3"

  if [[ "${DRY_RUN:-0}" == 1 ]]; then
    echo "[dry-run] would install $dest:"
    while IFS= read -r line; do
      echo "  $line"
    done <<<"$content"
    return 0
  fi

  if ! sudo -n test -d /etc/cron.d 2>/dev/null; then
    echo "[warn] /etc/cron.d not writable; install $label manually:" >&2
    echo "$content" >&2
    return 1
  fi

  echo "$content" | sudo tee "$dest" >/dev/null
  sudo chmod 644 "$dest"
  echo "[ok] installed $dest ($label)"
}

install_reboot_cron_d() {
  chmod +x "$REBOOT_SCRIPT"
  install_cron_d_file "$REBOOT_CRON_D" "$(reboot_cron_d_content)" "root @reboot reload"
}

install_health_cron_d() {
  chmod +x "$ENSURE_SCRIPT"
  install_cron_d_file "$HEALTH_CRON_D" "$(health_cron_d_content)" "*/15 (06–21h) health watchdog"
}

install_cron_ensure_systemd() {
  local src="$ROOT/scripts/systemd/${CRON_ENSURE_UNIT}.service"
  if [[ ! -f "$src" ]]; then
    return 1
  fi
  if ! command -v systemctl >/dev/null 2>&1; then
    return 0
  fi
  if [[ "$(systemctl is-system-running 2>/dev/null || echo unknown)" == "offline" ]]; then
    echo "[info] systemd offline (container/tini); skip ${CRON_ENSURE_UNIT}.service"
    return 0
  fi

  local tmp
  tmp="$(mktemp)"
  sed "s|%i|$ROOT|g" "$src" > "$tmp"

  if [[ "${DRY_RUN:-0}" == 1 ]]; then
    echo "[dry-run] would install $CRON_ENSURE_SERVICE and enable --now ${CRON_ENSURE_UNIT}.service"
    rm -f "$tmp"
    return 0
  fi

  if [[ "$(id -u)" -ne 0 ]] && ! sudo -n true 2>/dev/null; then
    echo "[warn] install boot ensure unit manually: sudo cp $src $CRON_ENSURE_SERVICE && sudo systemctl enable --now ${CRON_ENSURE_UNIT}.service" >&2
    rm -f "$tmp"
    return 1
  fi

  if [[ "$(id -u)" -eq 0 ]]; then
    install -m 644 "$tmp" "$CRON_ENSURE_SERVICE"
    systemctl daemon-reload
    systemctl enable --now "${CRON_ENSURE_UNIT}.service"
  else
    sudo install -m 644 "$tmp" "$CRON_ENSURE_SERVICE"
    sudo systemctl daemon-reload
    sudo systemctl enable --now "${CRON_ENSURE_UNIT}.service"
  fi
  rm -f "$tmp"
  echo "[ok] enabled ${CRON_ENSURE_UNIT}.service (boot ensure hook)"
}

run_ensure_only() {
  chmod +x "$ENSURE_SCRIPT"
  "$ENSURE_SCRIPT"
  save_cron_install_user "$(resolve_cron_install_user)"
  install_health_cron_d || true
  ensure_cron_boot_enabled || true
  install_cron_ensure_systemd || true
}

install_user_crontab() {
  local install_user="$1"
  shift
  local lines=( "$@" )

  if ! command -v crontab >/dev/null 2>&1; then
    echo "[err] crontab not installed. Install cron (e.g. apt install cron) first." >&2
    return 1
  fi

  save_cron_install_user "$install_user"

  local tmp
  tmp="$(mktemp)"
  if [[ "$(id -un)" == "$install_user" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      if is_tracker_cron_line "$line"; then
        continue
      fi
      printf '%s\n' "$line"
    done < <(crontab -l 2>/dev/null || true) > "$tmp"
    for line in "${lines[@]}"; do
      echo "$line" >> "$tmp"
    done
    crontab "$tmp"
  elif [[ "$(id -u)" -eq 0 ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      if is_tracker_cron_line "$line"; then
        continue
      fi
      printf '%s\n' "$line"
    done < <(crontab -u "$install_user" -l 2>/dev/null || true) > "$tmp"
    for line in "${lines[@]}"; do
      echo "$line" >> "$tmp"
    done
    crontab -u "$install_user" "$tmp"
  else
    rm -f "$tmp"
    echo "[err] cannot install crontab for $install_user (run as $install_user or root)" >&2
    return 1
  fi
  rm -f "$tmp"
  return 0
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
  if sudo -n service crond restart 2>/dev/null; then
    echo "[ok] cron daemon restarted (sudo service crond restart)"
    return 0
  fi
  if sudo -n systemctl restart crond 2>/dev/null; then
    echo "[ok] cron daemon restarted (sudo systemctl restart crond)"
    return 0
  fi
  if service cron restart 2>/dev/null; then
    echo "[ok] cron daemon restarted (service cron restart)"
    return 0
  fi
  echo "[warn] could not restart cron daemon automatically; run manually: sudo service cron restart" >&2
  return 1
}

if [[ "${ENSURE_ONLY:-0}" == 1 ]]; then
  if [[ "${DRY_RUN:-0}" == 1 ]]; then
    echo "[dry-run] would run: $ENSURE_SCRIPT"
    install_health_cron_d
    ensure_cron_boot_enabled || true
    install_cron_ensure_systemd || true
    exit 0
  fi
  run_ensure_only
  exit 0
fi

chmod +x "$WRAPPER"
mkdir -p "$ROOT/data"

lines=()
for time in "${TIMES[@]}"; do
  lines+=("$(cron_line_for_time "$time")")
done

if [[ "${REPAIR_CRONTAB:-0}" == 1 ]]; then
  install_user="$(resolve_cron_install_user)"
  if [[ "${DRY_RUN:-0}" == 1 ]]; then
    echo "[dry-run] would repair crontab for $install_user (${#lines[@]} slot(s))"
    for line in "${lines[@]}"; do
      echo "  $line"
    done
    exit 0
  fi
  if ! install_user_crontab "$install_user" "${lines[@]}"; then
    exit 1
  fi
  echo "[ok] crontab repaired for $install_user (${#lines[@]} slot(s))"
  restart_cron_daemon || true
  exit 0
fi

if [[ "${DRY_RUN:-0}" == 1 ]]; then
  echo "[dry-run] would install cron line(s):"
  for line in "${lines[@]}"; do
    echo "  $line"
  done
  echo "  log: $ROOT/data/daily_run.log"
  install_reboot_cron_d
  install_health_cron_d
  ensure_cron_boot_enabled || true
  install_cron_ensure_systemd || true
  exit 0
fi

install_user="$(resolve_cron_install_user)"
if ! install_user_crontab "$install_user" "${lines[@]}"; then
  exit 1
fi

echo "[ok] cron installed for $install_user (${#lines[@]} slot(s)):"
for line in "${lines[@]}"; do
  echo "     $line"
done
echo "     timezone: $TZ_NAME (system TZ should match for correct schedule)"
echo "     log: $ROOT/data/daily_run.log"
crontab -l | grep -E 'new-movie-tracker-daily' || true

install_reboot_cron_d || true
install_health_cron_d || true
ensure_cron_boot_enabled || true
install_cron_ensure_systemd || true
run_ensure_only

if ! restart_cron_daemon; then
  echo "[warn] crontab installed but cron may not pick up changes until restart" >&2
fi
