# Daily Run — External Scheduling (cron-independent)

**Problem:** On Cloud Agent container VM `bc-d4fb1f8c`, the cron daemon can die randomly. Health watchdog jobs live **inside** cron, so they cannot self-heal when cron is dead.

**Layers (use B + C + D on the cron VM):**

| Layer | Mechanism | Depends on cron? |
|-------|-----------|------------------|
| D | **Disable VM auto-sleep** (dashboard) | No |
| B | `daily_run_supervisor.sh` in tmux (repo) | No |
| C | `environment.json` `"start"` hook | No |
| A | Cursor `subscribe_timer` wake **5 min before** each slot | No |

Cron + `ensure_cron_running.sh` remain **best-effort backup** once cron is up.

---

## 铁律 — Timer wake subscriptions (mandatory)

Agents **must** keep these Cursor `subscribe_timer` wakes active on this Project. See also [SKILL.md §10 铁律](../SKILL.md).

### Required timers

| Beijing wake | Slot | UTC cron | Timer name |
|--------------|------|----------|------------|
| 06:55 | 07:00 daily | `55 22 * * *` | `daily-wake-0655-bj` |
| 12:55 | 13:00 daily | `55 4 * * *` | `daily-wake-1255-bj` |
| 19:55 | 20:00 daily | `55 11 * * *` | `daily-wake-1955-bj` |
| 17:55 | 18:00 forum-37 batch | `55 9 * * *` | `forum37-wake-1755-bj` |

Wake times are **Asia/Shanghai (北京时间)**. Cron expressions above are **UTC** (Beijing = UTC+8).

### On each timer fire

Project agent messages cron VM **`bc-d4fb1f8c`** (repo `/workspace`) to run:

```bash
./scripts/restart_daily_supervisor.sh
```

This script already runs `./scripts/ensure_cron_running.sh` first, then restarts the `daily-supervisor` tmux session. After forum-37 wake, also verify `crontab -l | grep forum37`.

### Deletion rule (mandatory)

**Never** call `unsubscribe` or remove any of the four timer wakes above without **explicit user confirmation in chat**. Do not delete, replace, or “clean up” subscriptions on your own initiative.

Before any `unsubscribe`, always run `list_subscriptions` (cursor-subscriptions MCP) and show the user what would be removed.

---

## Option D — Keep cloud VM awake (disable auto-sleep)

1. Open [cron VM environment settings](https://cursor.com/dashboard/cloud-agents/environments/e/d908b079-af28-11f1-bf4b-42ffb4d10ea7)
2. Disable **自动休眠** / **空闲后休眠** if available
3. Save start hook:

```json
{
  "install": "./scripts/setup_cron.sh",
  "start": "./scripts/restart_daily_supervisor.sh"
}
```

---

## Option B — VM supervisor (recommended, in repo)

```bash
cd /workspace
git pull origin main
./scripts/setup_cron.sh
tmux kill-session -t daily-supervisor 2>/dev/null || true
tmux new-session -d -s daily-supervisor -c /workspace \
  '/workspace/scripts/daily_run_supervisor.sh'
tail -f /workspace/data/supervisor.log
```

**Behavior:** Sleeps between 07:00 / 13:00 / 20:00 Beijing slot starts; polls every 5 min during each active window; runs `ensure_cron_running.sh` and triggers `daily_run.sh` when the slot is not yet logged today.

**Logs:** `data/supervisor.log`, `data/daily_run.log`

---

## Option A — Cursor subscribe_timer

See **铁律** above for required timer names and cron. Wakes the **Project conversation** 5 minutes before each slot so the cron VM is unfrozen before the poll window.

List subscriptions: `list_subscriptions` (cursor-subscriptions MCP).

---

## Option C — environment.json start hook

`restart_daily_supervisor.sh` runs on every VM wake when saved in the Cloud Agent environment dashboard.

---

## Forum-37 batch (daily 18:00 Beijing)

Separate from daily_run supervisor. Installed via `./scripts/setup_forum37_cron.sh` on cron VM **`bc-d4fb1f8c`**.

| Item | Value |
|------|-------|
| Schedule | Daily 18:00 Beijing |
| Crontab | `0 18 * * * TZ=Asia/Shanghai .../forum37_batch_run.sh` |
| Timer wake | `forum37-wake-1755-bj` at 17:55 Beijing (`55 9 * * *` UTC) |
| Log | `data/forum37_batch_run.log` |

Forum-37 is **cron-only** (not driven by `daily_run_supervisor.sh`). The 17:55 timer ensures cron is alive before 18:00.

---

## Verification checklist

- [ ] Four timer subscriptions present (`list_subscriptions`)
- [ ] Environment dashboard: auto-sleep disabled when possible (Option D)
- [ ] Start hook saved (Option C)
- [ ] `tmux ls` shows `daily-supervisor`
- [ ] After each slot, `data/daily_run.log` has a new start entry in the correct hour window
