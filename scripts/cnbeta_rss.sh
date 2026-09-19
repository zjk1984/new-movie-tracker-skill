#!/usr/bin/env bash
# CNBeta RSS fetch + Feishu notify (loads .env.local via cnbeta_rss.py).
# Install cron: scripts/setup_cron.sh  (default 07:00 + 13:00 + 20:00 Asia/Shanghai)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p data
export TZ="${TZ:-Asia/Shanghai}"
{
  echo "===== $(date -Iseconds) cnbeta_rss.sh start (TZ=$TZ) ====="
  export PYTHONUNBUFFERED=1
  python3 scripts/cnbeta_rss.py
  ec=$?
  echo "===== $(date -Iseconds) cnbeta_rss.sh exit $ec ====="
  exit "$ec"
} >> data/cnbeta_rss.log 2>&1
