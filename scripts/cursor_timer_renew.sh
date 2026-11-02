#!/usr/bin/env bash
# Cursor subscribe_timer specs + local expiry cache for cron VM bc-d4fb1f8c.
# MCP subscribe/list/unsubscribe only from the Cloud Agent (not callable from cron alone).
# See docs/daily-run-external-schedule.md and data/cursor_timer_renewal.log
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE_FILE="$ROOT/data/cursor_timer_subscriptions.json"
RENEW_LOG="$ROOT/data/cursor_timer_renewal.log"
RENEW_WINDOW_SEC="${CURSOR_TIMER_RENEW_WINDOW_SEC:-259200}" # 72h
EXPIRES_IN_SEC="${CURSOR_TIMER_EXPIRES_IN_SEC:-604800}"     # 7d (platform may cap)

mkdir -p "$ROOT/data"

log_renew() {
  printf '%s %s\n' "$(date -Is)" "$*" >>"$RENEW_LOG"
}

# name|utc_cron|wake_prompt (slot timers run restart; hourly runs heartbeat)
TIMER_SPECS=(
  'daily-wake-0655-bj|55 22 * * *|Cron VM bc-d4fb1f8c — 06:55 Beijing pre-07:00 daily slot wake. Run: cd /workspace && ./scripts/restart_daily_supervisor.sh. Then mandatory timer auto-renew: cursor-subscriptions list_subscriptions; if any of daily-wake-0655-bj, daily-wake-1255-bj, daily-wake-1955-bj, hourly-wake-non-slot-bj is missing OR expiresAt within 72h UTC, unsubscribe all four subscription IDs then subscribe_timer each per ./scripts/cursor_timer_renew.sh --json-spec (expiresInSeconds 604800). Run ./scripts/cursor_timer_renew.sh --record with list_subscriptions JSON on stdin. Reply one line: tmux ls + earliest expiresAt among the four.'
  'daily-wake-1255-bj|55 4 * * *|Cron VM bc-d4fb1f8c — 12:55 Beijing pre-13:00 daily slot wake. Run: cd /workspace && ./scripts/restart_daily_supervisor.sh. Reply one line: tmux ls + last supervisor.log timestamp.'
  'daily-wake-1955-bj|55 11 * * *|Cron VM bc-d4fb1f8c — 19:55 Beijing pre-20:00 daily slot wake. Run: cd /workspace && ./scripts/restart_daily_supervisor.sh. Reply one line: tmux ls + last supervisor.log timestamp.'
  'hourly-wake-non-slot-bj|55 0,1,2,3,5,6,7,8,10,12,13,14,15,16,17,18,19,20,21,23 * * *|Cron VM bc-d4fb1f8c — non-slot hourly :55 Beijing checkpoint wake. Run: cd /workspace && ./scripts/hourly_wake_heartbeat.sh. Reply one line: tail -1 data/hourly_wake.log.'
)

timer_names() {
  local spec name _cron _prompt
  for spec in "${TIMER_SPECS[@]}"; do
    IFS='|' read -r name _cron _prompt <<<"$spec"
    echo "$name"
  done
}

emit_json_spec() {
  python3 - "$EXPIRES_IN_SEC" "${TIMER_SPECS[@]}" <<'PY'
import json, sys

expires_in = int(sys.argv[1])
timers = []
for line in sys.argv[2:]:
    name, cron, prompt = line.split("|", 2)
    timers.append(
        {
            "name": name,
            "cron": cron,
            "expiresInSeconds": expires_in,
            "prompt": prompt,
        }
    )
print(json.dumps({"timers": timers, "exclude": ["forum37-wake-1755-bj"]}, indent=2))
PY
}

record_from_stdin() {
  local tmp
  tmp="$(mktemp)"
  trap 'rm -f "$tmp"' RETURN
  cat >"$tmp"
  python3 - "$STATE_FILE" "$tmp" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path

path = sys.argv[1]
raw = Path(sys.argv[2]).read_text(encoding="utf-8")
if not raw.strip():
    sys.exit("empty input for --record")
data = json.loads(raw)
subs = data.get("subscriptions", data if isinstance(data, list) else [])
required = {
    "daily-wake-0655-bj",
    "daily-wake-1255-bj",
    "daily-wake-1955-bj",
    "hourly-wake-non-slot-bj",
}
by_name = {}
for s in subs:
    args = s.get("subscriptionArgs") or {}
    name = args.get("name")
    if name in required:
        by_name[name] = {
            "subscriptionId": s.get("subscriptionId"),
            "expiresAt": s.get("expiresAt"),
            "cron": args.get("cron"),
        }
out = {
    "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "timers": by_name,
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)
    f.write("\n")
missing = required - set(by_name)
if missing:
    print(f"[warn] recorded partial set; missing: {', '.join(sorted(missing))}", file=sys.stderr)
else:
    print(f"[ok] recorded {len(by_name)} timers to {path}")
PY
}

warn_if_stale() {
  python3 - "$STATE_FILE" "$RENEW_WINDOW_SEC" "$RENEW_LOG" <<'PY'
import json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

state_path = Path(sys.argv[1])
window = int(sys.argv[2])
log_path = sys.argv[3]
required = [
    "daily-wake-0655-bj",
    "daily-wake-1255-bj",
    "daily-wake-1955-bj",
    "hourly-wake-non-slot-bj",
]
now = datetime.now(timezone.utc)

def log(msg: str) -> None:
    line = f"{now.astimezone().replace(microsecond=0).isoformat()} {msg}\n"
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)

if not state_path.is_file():
    log("[warn] cursor timer state missing; run MCP renew + cursor_timer_renew.sh --record (0655 wake or manual)")
    sys.exit(0)

try:
    state = json.loads(state_path.read_text(encoding="utf-8"))
except json.JSONDecodeError:
    log("[warn] cursor timer state corrupt; re-run --record after list_subscriptions")
    sys.exit(0)

timers = state.get("timers") or {}
issues = []
for name in required:
    row = timers.get(name)
    if not row or not row.get("expiresAt"):
        issues.append(f"{name}: missing")
        continue
    exp = datetime.fromisoformat(row["expiresAt"].replace("Z", "+00:00"))
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp - now <= timedelta(seconds=window):
        issues.append(f"{name}: expires {row['expiresAt']} (within {window}s)")

if issues:
    log("[warn] cursor timer renewal needed: " + "; ".join(issues))
PY
}

print_agent_steps() {
  cat <<EOF
Cursor timer auto-renew (4 timers; skip forum37-wake-1755-bj):

1. cursor-subscriptions list_subscriptions
2. If any required timer is missing OR expiresAt within 72h (UTC):
   a. cursor-subscriptions unsubscribe each existing subscriptionId for the four names
   b. For each entry in: ./scripts/cursor_timer_renew.sh --json-spec
      cursor-subscriptions subscribe_timer (name, cron, prompt, expiresInSeconds)
3. list_subscriptions again → ./scripts/cursor_timer_renew.sh --record (pipe JSON stdin)
4. Optional: tail data/cursor_timer_renewal.log

Daily automation: daily-wake-0655-bj prompt includes steps 1–3 after restart_daily_supervisor.sh.
EOF
}

case "${1:-}" in
  --json-spec)
    # shellcheck disable=SC2046
    emit_json_spec $(printf '%s\n' "${TIMER_SPECS[@]}")
    ;;
  --record)
    record_from_stdin
    ;;
  --warn-if-stale)
    warn_if_stale
    ;;
  --agent-renew|--print-steps)
    print_agent_steps
    ;;
  -h|--help)
    cat <<EOF
Usage: $(basename "$0") [--json-spec|--record|--warn-if-stale|--agent-renew]

  --json-spec       JSON array of 4 subscribe_timer payloads (single source of truth)
  --record          Read list_subscriptions JSON from stdin → data/cursor_timer_subscriptions.json
  --warn-if-stale   Append to data/cursor_timer_renewal.log if cache missing or expiry within ${RENEW_WINDOW_SEC}s
  --agent-renew     Human/agent checklist for MCP renew

State: $STATE_FILE
Log:   $RENEW_LOG
EOF
    ;;
  *)
    echo "[err] unknown argument: ${1:-}" >&2
    exit 1
    ;;
esac
