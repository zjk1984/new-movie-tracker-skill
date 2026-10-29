#!/usr/bin/env bash
# PikPak downloads/JAV dedupe (UC > C > size; cross-folder keeps downloads) plus
# optional JAV JavDB low-score report (rating < 4; off when PIKPAK_JAV_LOW_SCORE=0)
# and domestic small-file purge in My Pack (<30 MiB 国产). Default: dry-run.
# Cron: PIKPAK_DEDUPE_CRON=1 ./scripts/setup_cron.sh
# Apply on cron VM: PIKPAK_DEDUPE_APPLY=1 PIKPAK_DEDUPE_CRON=1 ./scripts/setup_cron.sh
# Cron line sets PIKPAK_JAV_LOW_SCORE=0 and PIKPAK_JAV_SCRAPE_CRON=1 (incremental
# Jellyfin sidecars in downloads after successful dedupe; log: pikpak_jav_scrape_cron.log).
# Multi-folder (nightly default): PIKPAK_DEDUPE_FOLDERS=downloads,JAV
# Domestic small purge folders: PIKPAK_DEDUPE_DOMESTIC_FOLDERS=My Pack (same python run)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p data
export TZ="${TZ:-Asia/Shanghai}"

export PIKPAK_DEDUPE_FOLDERS="${PIKPAK_DEDUPE_FOLDERS:-downloads,JAV}"
# Default My Pack only when unset; empty env (cron disable) must stay empty — use '-' not ':-'.
export PIKPAK_DEDUPE_DOMESTIC_FOLDERS="${PIKPAK_DEDUPE_DOMESTIC_FOLDERS-My Pack}"

ARGS=(--folders "$PIKPAK_DEDUPE_FOLDERS")
if [[ -n "${PIKPAK_DEDUPE_PARENT:-}" ]]; then
  ARGS+=(--parent "$PIKPAK_DEDUPE_PARENT")
fi
case "${PIKPAK_DEDUPE_APPLY:-0}" in
  1|true|yes|on) ARGS+=(--apply) ;;
esac

jav_scrape_cron_enabled() {
  case "${PIKPAK_JAV_SCRAPE_CRON:-0}" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

{
  echo "===== $(date -Iseconds) pikpak_downloads_dedupe.sh start (TZ=$TZ folders=$PIKPAK_DEDUPE_FOLDERS) ====="
  export PYTHONUNBUFFERED=1
  python3 scripts/pikpak_downloads_dedupe.py "${ARGS[@]}"
  ec=$?
  echo "===== $(date -Iseconds) pikpak_downloads_dedupe.sh exit $ec ====="
  if [[ "$ec" -eq 0 ]] && jav_scrape_cron_enabled; then
    {
      echo "===== $(date -Iseconds) pikpak_downloads_jav_scrape.py cron start ====="
      export PYTHONUNBUFFERED=1
      set +e
      python3 scripts/pikpak_downloads_jav_scrape.py --apply
      scrape_ec=$?
      set -e
      echo "===== $(date -Iseconds) pikpak_downloads_jav_scrape.py cron exit $scrape_ec ====="
    } >> data/pikpak_jav_scrape_cron.log 2>&1
    ec=$scrape_ec
  fi
  exit "$ec"
} >> data/pikpak_dedupe.log 2>&1
