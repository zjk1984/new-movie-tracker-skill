#!/usr/bin/env bash
# Scan the next 10 forum-142 list pages (auto-advances page cursor after each run).
# Usage:
#   ./scripts/forum142_batch_run.sh
#   ./scripts/forum142_batch_run.sh --status
#   ./scripts/forum142_batch_run.sh --reset
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p data reports
{
  echo "===== $(date -Iseconds) forum142_batch_run.sh start ====="
  export PYTHONUNBUFFERED=1
  python3 -u scripts/forum142_batch_run.py --headless "$@"
  ec=$?
  echo "===== $(date -Iseconds) forum142_batch_run.sh exit $ec ====="
  exit "$ec"
} >> data/forum142_batch_run.log 2>&1
