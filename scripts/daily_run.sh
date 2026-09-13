#!/usr/bin/env bash
# Daily scan + incremental PikPak download.
# Install cron: scripts/setup_cron.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p data
{
  echo "===== $(date -Iseconds) daily_run.sh start ====="
  export PYTHONUNBUFFERED=1
  python3 scripts/daily_run.py --headless
  ec=$?
  echo "===== $(date -Iseconds) daily_run.sh exit $ec ====="
  exit "$ec"
} >> data/daily_run.log 2>&1
