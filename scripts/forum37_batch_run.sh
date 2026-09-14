#!/usr/bin/env bash
# Scan the next 10 forum-37 list pages (auto-advances page cursor after each run).
# Usage:
#   ./scripts/forum37_batch_run.sh
#   ./scripts/forum37_batch_run.sh --status
#   ./scripts/forum37_batch_run.sh --reset
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p data
{
  echo "===== $(date -Iseconds) forum37_batch_run.sh start ====="
  export PYTHONUNBUFFERED=1
  python3 -u scripts/forum37_batch_run.py --headless "$@"
  ec=$?
  echo "===== $(date -Iseconds) forum37_batch_run.sh exit $ec ====="
  exit "$ec"
} >> data/forum37_batch_run.log 2>&1
