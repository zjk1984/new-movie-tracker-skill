#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/scripts/cursor_timer_renew.sh"

chmod +x "$SCRIPT"
"$SCRIPT" --help | grep -q json-spec
"$SCRIPT" --json-spec | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['exclude'] == ['forum37-wake-1755-bj']
names = {t['name'] for t in d['timers']}
assert names == {
    'daily-wake-0655-bj',
    'daily-wake-1255-bj',
    'daily-wake-1955-bj',
    'hourly-wake-non-slot-bj',
}
assert all(t['expiresInSeconds'] == 604800 for t in d['timers'])
"
echo "[ok] test_cursor_timer_renew passed"
