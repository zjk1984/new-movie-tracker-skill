#!/usr/bin/env bash
# GuangYa downloads + JAV dedupe (06:45 BJ cron). Default: dry-run.
# Apply on cron VM: GUANGYA_DEDUPE_APPLY=1 GUANGYA_DEDUPE_CRON=1 ./scripts/setup_cron.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p data
export TZ="${TZ:-Asia/Shanghai}"

export GUANGYA_DEDUPE_FOLDERS="${GUANGYA_DEDUPE_FOLDERS:-downloads,JAV,Save}"
export GUANGYA_DEDUPE_CROSS_PRIORITY="${GUANGYA_DEDUPE_CROSS_PRIORITY:-downloads,Save,JAV}"
SUMMARY="$ROOT/scripts/guangya_dedupe_summary.py"
FEISHU="$ROOT/scripts/guangya_dedupe_feishu.py"

ARGS=(--folders "$GUANGYA_DEDUPE_FOLDERS")
case "${GUANGYA_DEDUPE_APPLY:-0}" in
  1|true|yes|on) ARGS+=(--apply) ;;
esac

jav_scrape_cron_enabled() {
  case "${GUANGYA_JAV_SCRAPE_CRON:-0}" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

maybe_feishu_dedupe_done() {
  if [[ "${1:-1}" -ne 0 ]]; then
    return 0
  fi
  if [[ -x "$FEISHU" ]]; then
    python3 "$FEISHU" || true
  fi
}

{
  python3 "$SUMMARY" reset
  echo "===== $(date -Iseconds) guangya_downloads_dedupe.sh start (TZ=$TZ folders=$GUANGYA_DEDUPE_FOLDERS) ====="
  export PYTHONUNBUFFERED=1
  python3 scripts/guangya_downloads_dedupe.py "${ARGS[@]}"
  ec=$?
  echo "===== $(date -Iseconds) guangya_downloads_dedupe.sh exit $ec ====="
  jav_scrape_ran=0
  if [[ "$ec" -eq 0 ]] && jav_scrape_cron_enabled; then
    jav_scrape_ran=1
    {
      echo "===== $(date -Iseconds) guangya_downloads_jav_scrape.py cron start ====="
      export PYTHONUNBUFFERED=1
      set +e
      python3 scripts/guangya_downloads_jav_scrape.py --apply
      scrape_ec=$?
      set -e
      echo "===== $(date -Iseconds) guangya_downloads_jav_scrape.py cron exit $scrape_ec ====="
    } >> data/guangya_jav_scrape_cron.log 2>&1
    ec=$scrape_ec
  fi
  if [[ "$ec" -eq 0 ]] && [[ -n "${GUANGYA_AUDIT_REPORT_JSON:-}" ]]; then
    echo "===== $(date -Iseconds) guangya_audit_incremental.py start ====="
    python3 scripts/guangya_audit_incremental.py --report "$GUANGYA_AUDIT_REPORT_JSON" --json-stdout || ec=$?
    echo "===== $(date -Iseconds) guangya_audit_incremental.py exit $ec ====="
  fi
  if [[ "$ec" -eq 0 ]]; then
    jav_scrape_skipped=1
    if [[ "$jav_scrape_ran" -eq 1 ]]; then
      jav_scrape_skipped=0
    fi
    python3 "$SUMMARY" merge --json "$(python3 - <<PY
import json
print(json.dumps({
    "jav_scrape_ran": bool(${jav_scrape_ran}),
    "jav_scrape_skipped": bool(${jav_scrape_skipped}),
}))
PY
)"
    maybe_feishu_dedupe_done "$ec"
  fi
  exit "$ec"
} >> data/guangya_dedupe.log 2>&1
