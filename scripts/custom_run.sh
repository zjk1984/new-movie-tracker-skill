#!/usr/bin/env bash
# Custom page-range scan + PikPak + report.
# Example: ./scripts/custom_run.sh --start-page 5 --max-pages 20 --urls https://www.sehuatang.org/forum-37-1.html
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p data
{
  echo "===== $(date -Iseconds) custom_run.sh start ====="
  export PYTHONUNBUFFERED=1
  python3 scripts/custom_run.py --headless "$@"
  ec=$?
  echo "===== $(date -Iseconds) custom_run.sh exit $ec ====="
  exit "$ec"
} >> data/custom_run.log 2>&1
