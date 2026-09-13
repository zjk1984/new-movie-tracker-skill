#!/usr/bin/env bash
# Daily scan + incremental PikPak download.
# Cron example (07:00 local): 0 7 * * * /path/to/new-movie-tracker-skill/scripts/daily_run.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p data
exec python3 scripts/daily_run.py --headless >> data/daily_run.log 2>&1
