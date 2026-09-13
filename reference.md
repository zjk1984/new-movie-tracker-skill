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
| `--urls` | forum-2 + forum-103 + forum-37 | Target forum URLs to scan. |
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

**Kept** (`selected_download` preserved, submitted to PikPak):

| Region | Examples |
|--------|----------|
| `jav_censored` | MIDA-749, SNOS-270, [有码高清] |
| `uncensored` | ATID-799 无码破解, HEYZO (日本无码) |
| `domestic_leak` | [国产无码] …**私拍** / **泄密** / **流出** / **AI增强** (`domestic_subtype`) |

**Excluded** (magnets cleared, `skip_reason: excluded_*`):

| Region | Examples |
|--------|----------|
| `domestic_other` | [国产无码] 探花、推特、OnlyFans、剧情（无私拍/泄密/流出） |
| `western` | Blacked, Brazzers, 欧美 |
| `fc2` | FC2-PPV-* |
| `amateur` | MAAN-*, 348NTR-*, 200GANA-*, 229SCUTE-* |
| `other` | [主播录制] 等 |

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

### Environment variables

| Variable | Description |
|----------|-------------|
| `JAVDB_HOST` | API base URL (default mirror `https://jdforrepam.com`) |
| `JAVDB_TOKEN` | Optional bearer token (overrides saved login) |
| `JAVDB_AUTH_FILE` | Path to saved login JSON (default `<skill-dir>/javdb_auth.json`) |
| `JAVDB_DEVICE_UUID` | Stable device id for API params |

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

## Daily Schedule (07:00, incremental download)

`scripts/daily_run.py` scans **forum-2** (今日下载链接) + forum-103 + forum-37, applies cnsub-first + content filter, then submits **only new downloads** to PikPak (dedup via `download_state.json` in the output directory).

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

### Windows Task Scheduler (07:00)

1. Open **Task Scheduler** → **Create Basic Task**
2. Name: `NewMovieTracker-Daily`
3. Trigger: **Daily** → **07:00:00** (local time)
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

### Linux cron (07:00)

```cron
0 7 * * * /path/to/new-movie-tracker-skill/scripts/daily_run.sh
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
- When a post has **no magnet links**, the scanner collects from the thread body: `ed2k://`, `PikPak://`, `filename|size|hash` pipe codes, and labeled 哈希校验/特征码 (`hash_entries`).
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
