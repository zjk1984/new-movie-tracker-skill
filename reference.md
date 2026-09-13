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
| `--urls` | forum-103 + forum-36 | Target forum URLs to scan. |
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

**Kept** (`selected_magnet` preserved, submitted to PikPak):

| Region | Examples |
|--------|----------|
| `jav_censored` | MIDA-749, SNOS-270, [有码高清] |
| `uncensored` | ATID-799 无码破解, [无码高清] |

**Excluded** (magnets cleared, `skip_reason: excluded_*`):

| Region | Examples |
|--------|----------|
| `western` | Blacked, Brazzers, 欧美 |
| `fc2` | FC2-PPV-* |
| `amateur` | MAAN-*, 348NTR-*, 200GANA-*, 229SCUTE-* |
| `other` | Unrecognized numbering |

## Cnsub-first workflow

Magnet selection order (`scripts/magnet_select.py`):

1. **forum_cnsub** — title contains 中字/字幕/中文… and thread has magnet links
2. **javdb_cnsub** — JavDB lookup with cnsub filter + best magnet
3. **forum_fallback** — any magnet from the forum thread

End-to-end:

```bash
export PIKPAK_TOKEN="your-token"
python scripts/scan.py --days 3 --cnsub-priority --pikpak
python scripts/pikpak_download.py
python scripts/pikpak_download.py --all
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

## Scheduled Automation (Windows Task Scheduler)

After the first manual pass, you can enable `--headless` for background runs.

1. Search and open **Task Scheduler**.
2. Click **Create Basic Task**.
3. Name: `NewMovieTracker`
4. Trigger: **Daily** — set your preferred time.
5. Action: **Start a program**
   - Program/script: `python` (or full path to your python.exe)
   - Add arguments: `C:\Users\sakana\.qoderwork\skills\new-movie-tracker\scripts\scan.py --headless --days 3 --fetch-magnets --output-dir "C:\githubapp\project\new-movie-found"`
   - Start in: `C:\githubapp\project\new-movie-found`
6. Finish and open **Properties**.
7. Check **Run whether user is logged on or not**.
8. Uncheck **Start the task only if the computer is on AC power** (if on a laptop).

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
2. Set the token as an environment variable (do not commit it):

```bash
export PIKPAK_TOKEN="your-token-here"
```

For Cursor IDE, you can also set `PIKPAK_TOKEN` in **Settings → Secrets** so `${env:PIKPAK_TOKEN}` resolves automatically.

### Cloud Agent

Cloud Agents do not read local `~/.cursor/mcp.json`. Add the same server in [cursor.com/agents](https://cursor.com/agents) → **MCP**:

- **URL**: `https://api-open.mypikpak.com/mcp`
- **Header**: `Authorization: Bearer <your-token>`

Enable the PikPak MCP toggle when starting an agent run.

### Download workflow

After scanning, use the PikPak MCP `add_link` tool for each magnet. Default target folder is **My Pack** — pass its folder ID as `parent` (use `ls` at root to find it).

Fallback without MCP: `python scripts/pikpak_download.py` (uses the same token via `PIKPAK_TOKEN`).

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
