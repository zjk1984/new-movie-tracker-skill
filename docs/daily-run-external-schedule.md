# Daily Run — External Scheduling (cron-independent)

**Problem:** On Cloud Agent container VM `bc-d4fb1f8c`, the cron daemon can die randomly. Health watchdog jobs live **inside** cron, so they cannot self-heal when cron is dead.

**Layers (use B + C + D on the cron VM):**

| Layer | Mechanism | Depends on cron? |
|-------|-----------|------------------|
| D | **Disable VM auto-sleep** (dashboard) | No |
| B | `daily_run_supervisor.sh` in tmux (repo) | No |
| C | `environment.json` `"start"` hook | No |
| A | Cursor `subscribe_timer` wake at **:55 every hour** (Beijing) | No |

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

### Hourly :55 checkpoint wake (all Beijing hours)

**Added 2026-09-30** — prevents checkpoint freeze from causing missed cron/supervisor slots between daily windows.

Because `subscribe_timer` dedupes by cron expression (not name), non-slot hours use **one consolidated timer** instead of 20 separate subscriptions:

| Beijing hours covered | UTC cron | Timer name | Wake action on `bc-d4fb1f8c` |
|-----------------------|----------|------------|------------------------------|
| 00–05, 07–16, 18, 20–23 (20 hours) | `55 0,1,2,3,5,6,7,8,10,12,13,14,15,16,17,18,19,20,21,23 * * *` | `hourly-wake-non-slot-bj` | `./scripts/hourly_wake_heartbeat.sh` |

**Excluded from consolidated timer** (dedicated slot timers below — no double-fire):

| Beijing | Dedicated timer |
|---------|-----------------|
| 06:55 | `daily-wake-0655-bj` |
| 12:55 | `daily-wake-1255-bj` |
| 17:55 | `forum37-wake-1755-bj` |
| 19:55 | `daily-wake-1955-bj` |

Together: **24 Beijing :55 wakes/day**, **5 active subscriptions**.

`hourly_wake_heartbeat.sh` runs `ensure_cron_running.sh` only (no supervisor restart). Log: `data/hourly_wake.log`.

### On each timer fire

Project agent messages cron VM **`bc-d4fb1f8c`** (repo `/workspace`):

| Timer | Action |
|-------|--------|
| `daily-wake-0655-bj`, `daily-wake-1255-bj`, `daily-wake-1955-bj` | `./scripts/restart_daily_supervisor.sh` → verify `tmux ls` shows `daily-supervisor`, check `data/supervisor.log` |
| `forum37-wake-1755-bj` | `./scripts/ensure_cron_running.sh` → verify `crontab -l \| grep forum37` |
| `hourly-wake-non-slot-bj` | `./scripts/hourly_wake_heartbeat.sh` → verify `data/hourly_wake.log` and `data/cron_health.log` |

### Deletion rule (mandatory)

**Never** call `unsubscribe` or remove any of the five timer wakes above without **explicit user confirmation in chat**. Do not delete, replace, or “clean up” subscriptions on your own initiative.

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

See **铁律** above. Wakes the **Project conversation** at Beijing **:55 every hour** so the cron VM is unfrozen before slots and between them.

**Active timer names (5):**

1. `daily-wake-0655-bj`
2. `daily-wake-1255-bj`
3. `daily-wake-1955-bj`
4. `forum37-wake-1755-bj`
5. `hourly-wake-non-slot-bj`

List subscriptions: `list_subscriptions` (cursor-subscriptions MCP). Re-subscribe before `expiresAt` (~7 days).

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

- [ ] Five timer subscriptions present (`list_subscriptions`)
- [ ] Environment dashboard: auto-sleep disabled when possible (Option D)
- [ ] Start hook saved (Option C)
- [ ] On cron VM `bc-d4fb1f8c`: `tmux ls` shows `daily-supervisor`
- [ ] On cron VM: `crontab -l` unchanged (daily + forum37 lines intact)
- [ ] After non-slot hourly wake: new line in `data/hourly_wake.log` and `data/cron_health.log`
- [ ] After each slot, `data/daily_run.log` has a new start entry in the correct hour window
