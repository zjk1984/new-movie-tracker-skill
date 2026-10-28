#!/usr/bin/env bash
# PikPak downloads folder dedupe (UC > C > size). Safe default: dry-run.
# Cron: PIKPAK_DEDUPE_CRON=1 ./scripts/setup_cron.sh
# Apply on cron VM: PIKPAK_DEDUPE_APPLY=1 PIKPAK_DEDUPE_CRON=1 ./scripts/setup_cron.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p data
export TZ="${TZ:-Asia/Shanghai}"

ARGS=(--folder "${PIKPAK_DEDUPE_FOLDER:-downloads}")
if [[ -n "${PIKPAK_DEDUPE_PARENT:-}" ]]; then
  ARGS+=(--parent "$PIKPAK_DEDUPE_PARENT")
fi
case "${PIKPAK_DEDUPE_APPLY:-0}" in
  1|true|yes|on) ARGS+=(--apply) ;;
esac

{
  echo "===== $(date -Iseconds) pikpak_downloads_dedupe.sh start (TZ=$TZ) ====="
  export PYTHONUNBUFFERED=1
  python3 scripts/pikpak_downloads_dedupe.py "${ARGS[@]}"
  ec=$?
  echo "===== $(date -Iseconds) pikpak_downloads_dedupe.sh exit $ec ====="
  exit "$ec"
} >> data/pikpak_dedupe.log 2>&1
