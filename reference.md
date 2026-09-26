# Reference: New Movie Tracker

## Installation

1. Install Python 3.9+ if not already installed.
2. Install Playwright and its browser binaries:

```bash
pip install -r requirements.txt
python -m playwright install
```

> If `playwright install` downloads slowly, you can often skip it because the script uses your locally installed Google Chrome instead of Playwright's Chromium.

## Actor List Management

### Default Behavior
The script prioritizes actor sources in this order:
1. `--actors` (direct names)
2. `--actors-file` (JSON file)
3. `--actors-dir` (folder names as actors)

After loading actors, the script also loads `--aliases-file` and expands each actor into its known Japanese / Chinese aliases before matching titles.

### Initialize from Directory
```bash
python scripts/scan.py --actors-dir "E:\sakana" --save-actors
```
This reads folder names from `E:\sakana` and saves them to `actors.json` in the skill directory for future use.

### Set Actors Directly (e.g., from verbal input)
```bash
python scripts/scan.py --actors 佐々木さき 楪カレン 五日市芽依 森日向子 --save-actors
```

### View Current Actors
Read `actors.json` in the skill directory. It contains a JSON object like:
```json
{
  "actors": ["佐々木さき", "楪カレン", ...],
  "updated": "2026-05-18T21:28:00"
}
```

### Japanese / Chinese Aliases

If the forum may use Chinese names, keep cross-language names in `aliases.json`:

```json
{
  "aliases": {
    "三上悠亜": ["三上悠亚"]
  }
}
```

You can also store aliases inline in `actors.json`:

```json
{
  "actors": [
    {
      "name": "三上悠亜",
      "aliases": ["三上悠亚"]
    }
  ]
}
```

Aliases are bidirectional: if the tracked actor is `三上悠亜`, titles containing `三上悠亚` match; if the tracked actor is `三上悠亚`, titles containing `三上悠亜` also match. The scanner additionally generates simple safe variants such as `々` expansion and common Japanese/traditional-to-simplified character changes.

## Script Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--actors` | `None` | Direct actor names (space-separated). Overrides file and directory. |
| `--actors-file` | `<skill-dir>/actors.json` | Path to JSON actor list. |
| `--aliases-file` | `<skill-dir>/aliases.json` | Path to Japanese / Chinese alias mapping. |
| `--actors-dir` | `E:\sakana` | Folder to read actor names from (fallback). |
| `--save-actors` | `False` | Save loaded actors back to `--actors-file`. |
| `--urls` | forum-2/95/142 + forum-103 + forum-37 | Target forum URLs to scan. |
| `--days` | `3` | Number of recent days to include. |
| `--max-pages` | `5` | Max pages to scan per forum. |
| `--headless` | `False` | Run without visible browser window. |
| `--output-dir` | `.` | Where to write results. |
| `--fetch-magnets` | `False` | Open matched threads and extract magnet links. |
| `--keyword` | `None` | Match posts whose title contains any keyword (e.g. `流出`). |
| `--since` / `--until` | `None` | Date range filter (`YYYY-MM-DD` or `YYYY-MM`). |
| `--start-page` | `1` | First forum page to scan. |
| `--javdb` | `False` | Enrich matched posts with JavDB metadata. |
| `--javdb-magnets` | `False` | Fetch magnets from JavDB API (implies `--javdb`). |
| `--javdb-best` | `False` | Keep only the best JavDB magnet. |
| `--javdb-cnsub` | `False` | Filter JavDB magnets to Chinese-subtitled entries. |
| `--javdb-hd` | `False` | Filter JavDB magnets to HD entries. |
| `--javdb-host` | mirror | JavDB API host (default `https://jdforrepam.com`). |
| `--cnsub-priority` | `False` | Cnsub-first magnet selection (implies `--fetch-magnets`). |
| `--pikpak` | `False` | Submit selected magnets to PikPak after scan. |
| `--pikpak-folder` | `My Pack` | PikPak target folder name. |
| `--all-regions` | `False` | Include western/FC2/amateur (default: 日本有码 + 无码 JAV). |

## Content filter (default)

### 日本 JAV

**Kept:**

| Region | Examples |
|--------|----------|
| `jav_censored` | MIDA-749, SNOS-270, [有码高清] |
| `uncensored` | ATID-799 无码破解, HEYZO (日本无码) |

### 国产无码（forum-2 / forum-95 / forum-142 等）

识别：标题含 `[国产无码]` / `国产无码` / `[国产]`（优先于普通无码关键字）。

**保留** `domestic_leak` — 满足任一且未命中排除项：

| `domestic_subtype` | 条件 |
|--------------------|------|
| 泄密 | 泄密 / 泄露 |
| 流出 | 流出（不含「未流出」） |
| AI增强 | AI增强 / AI 增强 |
| 熟女自拍 | 熟女 |
| 露脸 | 露脸 |
| 真实 | 真实 |
| 大胸 | 大胸 |
| 少妇 | 少妇 |
| 美女 | 美女 |
| 学生 | 学生 |
| 老师 | 老师 |
| ed2k | 标题 ed2k/115Ed2k/115eD2k 或帖内 `ed2k://` 链接 |

**排除** `domestic_other` — 命中即排除（优先级高于保留标签）：

| 原因 | 条件 |
|------|------|
| 私拍 | 私拍 |
| 厕拍 | 厕拍 |
| 黑人 | 黑人 |
| 情色分享 | 情色分享 |
| AI增强 | AI增强 / AI 增强 |
| AI短剧 | AI短剧 / AI真人短剧 |
| 酒店偷拍 | 酒店偷拍 |
| 伪番号 | XJX, JDSY, MDSY, MDSR, JDSC, CNXX, RXAJ, TMW, TMG, YCM + 数字 |
| OnlyFans | OnlyFans, HongKongDoll, 玩偶姐姐 |

其他国产（探花、推特、剧情、福利姬等）→ `domestic_other`（仍保留原始 `magnets[]` / `hash_entries[]`，仅跳过 PikPak 提交）。

### 其他排除

| Region | Examples |
|--------|----------|
| `western` | Blacked, Brazzers, 欧美 |
| `fc2` | FC2-PPV-* |
| `amateur` | MAAN-*, 348NTR-*, 200GANA-*, 229SCUTE-* |
| `other` | [主播录制] 等 |

Implementation: `scripts/content_filter.py`. Disable all filters: `--all-regions`.

## Cnsub-first workflow

Magnet selection order (`scripts/magnet_select.py`):

1. **forum_cnsub** — title contains 中字/字幕/中文… and thread has magnet links
2. **javdb_cnsub** — JavDB lookup with cnsub filter + best magnet
3. **forum_fallback** — any magnet from the forum thread

End-to-end:

```bash
python scripts/pikpak_login.py login
python scripts/scan.py --days 3 --cnsub-priority --pikpak
python scripts/pikpak_download.py --new-only
python scripts/pikpak_download.py --all --new-only
```

With PikPak MCP: scan with `--cnsub-priority` only, then MCP `add_link` each `selected_magnet` into **My Pack**.

## JavDB API

The skill includes a Python port of [zjk1984/javdb-cli](https://github.com/zjk1984/javdb-cli) mobile App API client in `scripts/javdb_client.py`. It signs requests with the `jdsignature` header and calls `/api/v2/search`, `/api/v4/movies/{id}`, and `/api/v1/movies/{id}/magnets`.

Requires `curl_cffi` (plain `requests` often gets HTTP 400 from JavDB).

### Standalone lookup

```bash
python scripts/javdb_lookup.py SSIS-589 --magnets --best --json
python scripts/javdb_lookup.py MIDA-749 --magnets --cnsub
```

### Scan + JavDB

```bash
python scripts/scan.py --keyword 流出 --javdb --javdb-magnets --javdb-best --fetch-magnets
```

Forum magnets and JavDB magnets are merged (deduplicated). When forum threads only have `.torrent` attachments, JavDB often still provides usable magnet links.

### JavDB query report (default on)

Each kept 有码/无码 item gets `javdb_query`:

| Field | Meaning |
|-------|---------|
| `content_type_label` | `有码` or `无码` (from JavDB title/number) |
| `magnet_status` | `available` / `empty` / `error` |
| `magnet_total` | Total magnets on JavDB |
| `magnet_filtered` | After `--cnsub`/`--hd` filter |
| `best_magnet` | Best magnet URI |
| `summary` | One-line Chinese explanation for chat |

`last_result.json` includes `javdb_summary` aggregate counts.

Disable with `--no-javdb-query`.

### JavDB download gates (Japanese + gated domestic)

Before PikPak submit, `scripts/javdb_client.py` applies gates in order: **tags** → **reviews_count** → **watched_count** → **score** (default min 4.0, `JAVDB_MIN_DOWNLOAD_SCORE`).

Applies to Japanese **有码/无码/FC2** and to **国产** (`domestic_leak`) posts that have an AV number **and** a successful JavDB lookup (`query_status: ok`). Domestic posts without a number, or when JavDB lookup fails, keep the previous behavior (no JavDB gate).

**Popularity gates** (`reviews_count` = rating count, `watched_count` = App「评价」/看过人数; Asia/Shanghai calendar):

| Release timing | `reviews_count` | `watched_count` |
|----------------|-----------------|-----------------|
| Within 7 calendar days of release | 0 or missing (pass) | 0 or missing (pass) |
| 8–30 calendar days after release | ≥ 10 | ≥ 10 |
| Current year (older than 30 days) | ≥ 100 | ≥ 100 |
| Prior years | ≥ 1000 | ≥ 500 |

**Watched compensation track** (prior years only, when standard watched threshold fails): `reviews_count` ≥ prior-year threshold, `score` ≥ `JAVDB_COMP_MIN_SCORE` (default 4.0), `watched_count` ≥ `JAVDB_COMP_WATCHED_FLOOR` (default 250). Sets `javdb_query.javdb_gate_path` to `watched_compensation`. Pipeline order unchanged (`reviews` must pass before compensation is evaluated).

Missing `release_date` fails. Missing count fails for releases older than 7 days. Constants: `JAVDB_ZERO_REVIEWS_DAYS`, `JAVDB_RECENT_RELEASE_DAYS`, `JAVDB_RECENT_MIN_REVIEWS`, `JAVDB_COMP_WATCHED_FLOOR`, `JAVDB_COMP_MIN_SCORE`.

Skip reasons: `javdb_no_release_date`, `javdb_no_reviews_count`, `javdb_reviews_low_{n}`, `javdb_no_watched_count`, `javdb_watched_low_{n}`.

Summary labels: `watched_count` → 「看过 N 人」; `reviews_count` → 「评分 N 人」; `score` → 「均分 X.XX」.

### Environment variables

| Variable | Description |
|----------|-------------|
| `JAVDB_HOST` | API base URL (default mirror `https://jdforrepam.com`) |
| `JAVDB_TOKEN` | Optional bearer token (overrides saved login) |
| `JAVDB_AUTH_FILE` | Path to saved login JSON (default `<skill-dir>/javdb_auth.json`) |
| `JAVDB_DEVICE_UUID` | Stable device id for API params |
| `JAVDB_COMP_WATCHED_FLOOR` | Prior-year watched compensation floor (default `250`) |
| `JAVDB_COMP_MIN_SCORE` | Min score for watched compensation track (default `4.0`) |

### Login

```bash
python scripts/javdb_login.py login
python scripts/javdb_login.py status --check
python scripts/javdb_login.py logout
```

- Token is stored locally in `javdb_auth.json` (mode 600, gitignored).
- `--save-password` stores password in plaintext for manual re-login only; off by default.
- Priority: `JAVDB_TOKEN` env → saved token in `javdb_auth.json` → anonymous.

## First Run (Pass Cloudflare)

Run without `--headless` so a Chrome window opens:

```bash
python scripts/scan.py --days 3 --fetch-magnets
```

If a Cloudflare challenge appears, complete it manually in the opened window. The script waits up to 90s. After success, cookies are saved in `chrome_profile/` inside the output directory.

## Daily Schedule (07:00 + 13:00 + 20:00 Asia/Shanghai, incremental download)

`scripts/daily_run.py` scans **forum-2 / forum-95 / forum-142** (今日下载链接) + forum-103 + forum-37, applies cnsub-first + content filter, then submits **only new downloads** to PikPak (dedup via `download_state.json` in the output directory).

**Timezone:** schedules use **Asia/Shanghai (北京时间, UTC+8)** — the same default as report timestamps in `env_utils.py`. GitHub Actions is not used: the run needs a local Chrome profile, Cloudflare session, and PikPak credentials on the host machine.

### Prepare once

1. Save PikPak token (persisted in skill directory, like JavDB):

```bash
python scripts/pikpak_login.py login
python scripts/pikpak_login.py login --from-env   # import from .env.local / PIKPAK_TOKEN
python scripts/pikpak_login.py status --check
```

Stored in `pikpak_auth.json` (gitignored, mode 600). Priority: `PIKPAK_TOKEN` env → saved file.

2. First Cloudflare pass (headed browser):

```bash
python scripts/daily_run.py --no-headless
```

3. Verify output under `data/` (`last_result.json`, `download_state.json` after first download).

### Manual daily command

```bash
python scripts/daily_run.py --headless
python scripts/daily_run.py --download-only   # re-submit from existing scan
python scripts/pikpak_download.py --new-only --all
```

| Flag | Default | Description |
|------|---------|-------------|
| `--output-dir` | `<skill>/data` | Results + state + chrome profile |
| `--days` | `2` | Recent days to scan (dedup handles overlap) |
| `--scan-only` | off | Scan without PikPak |
| `--download-only` | off | PikPak new-only from last scan |
| `--pikpak-folder` | `My Pack` | Target folder |

Incremental logic (`download_state.json`):
- Skip if **btih** hash already submitted
- Skip if **thread href** already submitted (same post)

### Windows Task Scheduler (07:00 Asia/Shanghai)

Set Windows system timezone to **(UTC+08:00) Beijing** (or run at 07:00 local if the machine is already in China Standard Time).

1. Open **Task Scheduler** → **Create Basic Task**
2. Name: `NewMovieTracker-Daily`
3. Trigger: **Daily** → **07:00:00**
4. Action: **Start a program**
   - Program: `C:\path\to\new-movie-tracker-skill\scripts\daily_run.bat`
   - Start in: `C:\path\to\new-movie-tracker-skill`
5. Properties → **Run whether user is logged on or not**; disable “AC power only” on laptops
6. Logs append to `data/daily_run.log`

Or use `python` directly:

```
Program: C:\Python311\python.exe
Arguments: scripts\daily_run.py --headless
Start in: C:\path\to\new-movie-tracker-skill
```

### Linux cron (07:00 + 13:00 + 20:00 Asia/Shanghai)

One-liner install (recommended):

```bash
./scripts/setup_cron.sh
```

Installs **three** user-crontab slots (07:00, 13:00, and 20:00 Beijing), two **root `/etc/cron.d`** hooks, boot ensure logic, and verifies **`systemctl enable --now cron`** when systemd is available. Requires system timezone **Asia/Shanghai** (Vixie cron uses system local time for scheduling). The installer **automatically attempts to restart the cron daemon** after updating crontab. If that fails, run **`sudo service cron restart`** manually (required on some cloud VMs).

| File | Purpose |
|------|---------|
| `/etc/cron.d/new-movie-tracker-reboot` | `@reboot` → `scripts/cron_reboot_reload.sh` (reload when cron starts; log `data/cron_reboot.log`) |
| `/etc/cron.d/new-movie-tracker-health` | `*/15` (06:00–21:59) + `0,30` otherwise → `scripts/ensure_cron_running.sh` **as install user** (auto-fix; log `data/cron_health.log`) |
| `data/cron_install_user` | Username whose crontab holds the daily slots (written by `setup_cron.sh`) |
| `scripts/ensure_cron_running.sh` | Start/restart cron if down; verify **install user's** crontab; auto-repair — **run at container boot** |
| `new-movie-tracker-cron-ensure.service` | Optional systemd oneshot at boot (full systemd hosts only) |

**Why `@reboot` failed on container VMs (2026-09-18):** Cloud Agent / container VMs often use **`/tini` as PID 1**, not full systemd. Cron may start **hours after VM boot** (e.g. boot 02:44, cron 09:10). `@reboot` jobs only fire when the **cron daemon starts**, not when the VM boots — so the 07:00 slot is missed and `cron_reboot.log` is never created until cron finally starts. **`systemctl enable cron` alone does not help** when systemd is offline.

**Fix for late-start / dying cron on containers:** cron and its health watchdog are **best-effort only** — if the cron daemon dies, jobs inside cron never fire. Use an **external supervisor** that runs outside cron:

```bash
# After ./scripts/setup_cron.sh — keep running in tmux on the cron VM
tmux new-session -d -s daily-supervisor -c /path/to/new-movie-tracker-skill \
  './scripts/daily_run_supervisor.sh'
```

| File | Purpose |
|------|---------|
| `scripts/daily_run_supervisor.sh` | Sleeps between slot starts; polls every 5 min during each pending slot window; waits while `daily_run.sh` runs |
| `scripts/lib/daily_run_slots.sh` | Slot log detection + `seconds_until_next_slot_start()` for supervisor sleep/poll timing |
| `data/supervisor.log` | Supervisor actions and ensure-cron output |

Supervisor poll windows (Beijing, from slot start until next slot start):

| Slot | Poll from | Poll until | Log match (idempotent) |
|------|-----------|------------|------------------------|
| 07:00 | 07:00 | 13:00 | `daily_run.sh start` with hour 07–12 |
| 13:00 | 13:00 | 20:00 | hour 13–19 |
| 20:00 | 20:00 | 07:00 next day | hour 20–23 (late catch-up e.g. 21:43 counts) |

Between poll windows the supervisor sleeps until the next slot start (e.g. 06:50 → sleep until 07:00; after 07:00 slot logged → sleep until 13:00).

**VM wake / start hook** (required on checkpoint VMs — restarts supervisor so missed-slot catch-up runs):

Repo ships `environment.json`:

```json
{
  "install": "./scripts/setup_cron.sh",
  "start": "./scripts/restart_daily_supervisor.sh"
}
```

`restart_daily_supervisor.sh` runs `ensure_cron_running.sh`, kills stale `daily-supervisor` tmux (frozen after checkpoint restore), and starts a fresh `daily_run_supervisor.sh` so `catch_up_missed_slots_on_start` re-evaluates missed Beijing slots. Apply this `environment.json` to the cron VM Cloud Agent environment. Optional **Cursor `subscribe_timer`** wake at 07:00/13:00/20:00 — see project doc `daily-run-external-schedule.md`.

Supervisor one-shot check (no loop): `./scripts/daily_run_supervisor.sh --once`

**Root vs install-user crontab (2026-09-18):** Daily jobs live in the **install user's** crontab (`ubuntu` on Cloud Agent VMs), not root's. The health watchdog must run `ensure_cron_running.sh` **as that user** (or read `data/cron_install_user` and check with `crontab -u`). Running as root caused false "tracker crontab missing" warnings and warn-only behavior missed repairs before 13:00.

**Why not user `@reboot` + sudo?** Cron jobs run without a TTY and minimal `PATH`; `sudo service cron restart` often fails silently (`use_pty`, missing `/usr/sbin`).

Equivalent lines:

```cron
# /etc/cron.d/new-movie-tracker-reboot (root, installed by setup_cron.sh)
@reboot root /path/to/new-movie-tracker-skill/scripts/cron_reboot_reload.sh

# /etc/cron.d/new-movie-tracker-health (runs as install user — checks correct crontab)
*/15 6-21 * * * ubuntu /path/to/new-movie-tracker-skill/scripts/ensure_cron_running.sh
0,30 0-5,22-23 * * * ubuntu /path/to/new-movie-tracker-skill/scripts/ensure_cron_running.sh

# user crontab
0 7 * * * TZ=Asia/Shanghai /path/to/new-movie-tracker-skill/scripts/daily_run.sh # new-movie-tracker-daily
0 13 * * * TZ=Asia/Shanghai /path/to/new-movie-tracker-skill/scripts/daily_run.sh # new-movie-tracker-daily
0 20 * * * TZ=Asia/Shanghai /path/to/new-movie-tracker-skill/scripts/daily_run.sh # new-movie-tracker-daily
```

Custom slots: `./scripts/setup_cron.sh --time 07:00 --time 13:00 --time 20:00` or `DAILY_RUN_TIMES=07:00,13:00,20:00 ./scripts/setup_cron.sh`

Verify: `crontab -l | grep new-movie-tracker-daily` · Logs: `data/daily_run.log`, `data/cron_health.log`, `data/cron_reboot.log` · Dry-run: `./scripts/setup_cron.sh --dry-run` · Health check / auto-fix: `./scripts/setup_cron.sh --ensure-only` or `./scripts/ensure_cron_running.sh`

### Linux cron — forum-37 batch (daily 18:00 Asia/Shanghai)

Separate from daily_run slots. Scans the next 20 forum-37 list pages via `scripts/forum37_batch_run.sh` (auto-advances page cursor in `data/forum37_batch_state.json`). Default batch size is 20 pages (`PAGES_PER_RUN` / `--max-pages`); no env var override — only cron schedule uses `FORUM37_CRON_*`. An existing state file may still show `"pages_per_run": 10` from earlier runs; that field is record-only — each run uses the current default unless you pass `--max-pages`.

```bash
./scripts/setup_forum37_cron.sh
```

| Item | Value |
|------|-------|
| Schedule | **Daily 18:00** Beijing (`FORUM37_CRON_WEEKDAYS=*`) |
| Crontab line | `0 18 * * * TZ=Asia/Shanghai /path/to/scripts/forum37_batch_run.sh # new-movie-tracker-forum37-batch` |
| Log | `data/forum37_batch_run.log` |
| Cron VM | `bc-d4fb1f8c` — run after merge: `git pull && ./scripts/setup_forum37_cron.sh` |

Does not modify daily_run crontab lines. Optional **Cursor `subscribe_timer`** wake at **17:55 Beijing** daily (`55 9 * * *` UTC) so the cron VM is unfrozen before the 18:00 slot — see project doc `daily-run-external-schedule.md`.

Verify: `crontab -l | grep forum37` · Dry-run: `./scripts/setup_forum37_cron.sh --dry-run` · Remove: `./scripts/setup_forum37_cron.sh --remove`

### GitHub Actions schedule (07:00 Asia/Shanghai, optional)

Only if you run `daily_run` in CI with the required secrets and browser setup. **07:00 北京时间** equals:

```yaml
on:
  schedule:
    # Option A: UTC (GitHub default)
    - cron: '0 23 * * *'
    # Option B: explicit timezone (clearer)
    - cron: '0 7 * * *'
      timezone: Asia/Shanghai
```

Self-hosted cron/systemd remains the recommended path for Cloudflare + local `chrome_profile`.

### Linux systemd timer (07:00 Asia/Shanghai)

For servers using systemd instead of cron:

```bash
sudo ./scripts/setup_systemd_timer.sh
systemctl list-timers new-movie-tracker-daily.timer
sudo systemctl start new-movie-tracker-daily.service   # manual test
```

## Scheduled Automation (legacy scan-only)

For actor-list scans without PikPak dedup, you can still schedule `scan.py` directly:

```bash
python scripts/scan.py --headless --days 3 --fetch-magnets --output-dir ./data
```

## PikPak MCP

Connect PikPak cloud download to Cursor via the official MCP server.

### Project config

This repo includes `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "pikpak": {
      "url": "https://api-open.mypikpak.com/mcp",
      "headers": {
        "Authorization": "Bearer ${env:PIKPAK_TOKEN}"
      }
    }
  }
}
```

### Token setup

1. In PikPak, go to **Account & Security → Connected Apps → Personal Access Tokens** and create a token with `cloud_download` permission.
2. Save it in the skill directory:

```bash
python scripts/pikpak_login.py login
```

For **Cursor MCP**, also set `PIKPAK_TOKEN` in **Settings → Secrets** (MCP reads env only). Scripts and `daily_run.py` use `pikpak_auth.json` automatically.

### Feishu (Lark) notifications

Add to `.env.local` (gitignored):

| Variable | Description |
|----------|-------------|
| `FEISHU_APP_ID` | App ID from Feishu open platform (`cli_…`) |
| `FEISHU_APP_SECRET` | App secret |
| `FEISHU_RECEIVE_ID` | Target `chat_id` (group) or `open_id` / `user_id` |
| `FEISHU_RECEIVE_ID_TYPE` | Default `chat_id` |

App needs **im:message** or **im:message:send_as_bot** permission. Add the bot to the target group before sending.

```bash
python scripts/feishu_notify.py ping
python scripts/feishu_notify.py cards --reconstruct
python scripts/feishu_notify.py cards --input data/last_result.json --download-report data/download_report.json
python scripts/daily_run.py --headless   # report + Feishu when FEISHU_RECEIVE_ID is set
```

Each run saves `reports/{label}_{timestamp}.md` to GitHub (full fail/success link tables). Feishu card: scan summary + link to the MD file.

### Cloud Agent

Cloud Agents do not read local `~/.cursor/mcp.json`. Add the same server in [cursor.com/agents](https://cursor.com/agents) → **MCP**:

- **URL**: `https://api-open.mypikpak.com/mcp`
- **Header**: `Authorization: Bearer <your-token>`

Enable the PikPak MCP toggle when starting an agent run.

### Download workflow

After scanning, use the PikPak MCP `add_link` tool for each magnet. Default target folder is **My Pack** — pass its folder ID as `parent` (use `ls` at root to find it).

Fallback without MCP: `python scripts/pikpak_download.py` (uses saved token in `pikpak_auth.json`).

### PikPak feature codes (特征码 / GCID 秒传)

Format: `PikPak://filename|size_bytes|GCID_HASH` (40-char GCID, not btih/ed2k MD4).

```bash
python scripts/pikpak_download.py --sha 'PikPak://MIDA-749.mp4|6123456789|ABCDEF0123456789ABCDEF0123456789ABCD'
python scripts/pikpak_download.py --sha-file feature_codes.txt
```

- **Instant add** when PikPak cloud already has the GCID (`PHASE_TYPE_COMPLETE`).
- **Fails** if the hash is not cached (no offline fetch by hash alone).
- When a post has **no magnet links** (common for `[BT种子]` attachments), the scanner collects from the thread body: `ed2k://`, `PikPak://`, `filename|size|hash` pipe codes, and BT labels **【特征全码】/【哈希校验】/【特徵全碼】** — 40-char values become `magnet:?xt=urn:btih:HASH` (`hash_label_btih` in `hash_entries`).
- Selection order with magnets: cnsub forum → JavDB → forum fallback. **Without magnets:** PikPak SHA → ed2k → JavDB (if `--cnsub-priority`).
- **ed2k** links are submitted as URL offline tasks (different hash algorithm from GCID).

## Troubleshooting

**Chrome not found**
- Add your `chrome.exe` path to the `candidates` list in `scan.py`, or ensure Chrome is installed in a standard location.

**Cloudflare every run**
- Do not delete the `chrome_profile/` folder.
- Make sure your IP has not changed drastically (VPN switching can trigger re-validation).
- If Chrome is already running with your default profile, close it before the first run so Playwright can create the persistent profile.

**No posts parsed**
- The script saves `page_debug.html` and a screenshot. Share `page_debug.html` with the skill author to update parsing rules.

**Wrong actor matches**
- The script does simple substring matching (`name in post_title`) across actors and aliases. If names are too generic (e.g., `000`), rename them or remove them from `actors.json` / `aliases.json`.
