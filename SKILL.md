---
name: new-movie-tracker
description: Scan sehuatang.org forums for recent posts and match them against a maintained actor list to identify new releases and extract magnet links. Use when the user asks about actor updates, new movies, sehuatang monitoring, checking favorite actors for new works, forum post filtering, or magnet link extraction.
---

# New Movie Tracker

## Purpose
Monitor sehuatang.org forums for posts published in the last N days, match post titles against an actor list, and report which actors have new releases. Optionally open matched threads to extract magnet links, or fetch magnets and metadata from JavDB via its mobile App API (ported from [zjk1984/javdb-cli](https://github.com/zjk1984/javdb-cli)).

## When to Use
- The user asks to check sehuatang for updates
- The user wants to know which favorite actors have new works
- The user mentions filtering forum posts by actor names
- The user asks for magnet links from matched posts
- The user wants to add, remove, or manage their actor watchlist

## Actor List Management

The skill maintains its own actor list in `actors.json` inside the skill directory. Actors can be provided in several ways:

1. **Maintained JSON file** (default) — `actors.json` in the skill directory.
2. **Folder directory** — Folder names are treated as actor names (e.g., `E:\sakana`).
3. **Direct argument** — Pass names directly via `--actors`.

### Japanese / Chinese Name Aliases

Forum titles may use Chinese names while users provide Japanese names, or the reverse. When adding or updating actors:

- Always try to maintain the Japanese and Chinese names together.
- Store the user's primary tracking list in `actors.json`.
- Store cross-language aliases in `aliases.json` or as per-actor `aliases` entries in `actors.json`.
- If only one language is known, keep that name and add the other language later when it is discovered from search results or user input.

Supported alias formats:

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

or:

```json
{
  "aliases": {
    "三上悠亜": ["三上悠亚"]
  }
}
```

The scanner also generates a few safe variants automatically, such as `々` expansion (`佐々木` -> `佐佐木`) and common Japanese/traditional character simplifications (`亜` -> `亚`, `桜` -> `樱`).

### Initializing or Updating the List

If the user provides actor names verbally or via chat, update `actors.json` directly:
```bash
python scripts/scan.py --actors 佐々木さき 楪カレン 五日市芽依 --save-actors
```

To import from a folder and save to JSON:
```bash
python scripts/scan.py --actors-dir "<your-actor-folder>" --save-actors
```

To view the current list, read `actors.json`.

## Prerequisites
- Python 3.9+ installed on Windows
- `playwright`, `curl_cffi`, and `requests` Python packages
- Google Chrome installed

## Workflow

### 1. Verify Environment
Check that `scripts/scan.py` exists in the skill directory. If the user has not installed dependencies, instruct them to run:
```bash
pip install -r requirements.txt
python -m playwright install
```

### 2. Ensure Actor List Exists
Check `actors.json` in the skill directory. If it is missing or empty, ask the user for their actor list or guide them to initialize it from a directory or direct arguments.

If the user provides Japanese-only or Chinese-only names, add the known cross-language aliases to `aliases.json` when available. Do not delete the original name just because an alias was added.

### 3. Run Scan
Execute the utility script from the skill directory. Default invocation scans both forum-103 and forum-36:
```bash
python scripts/scan.py --days 3 --fetch-magnets
```

If the user wants to override actors for a single run:
```bash
python scripts/scan.py --actors 佐々木さき 楪カレン --days 3
```

### 4. Handle Cloudflare
If the script reports a Cloudflare challenge:
- In headed mode (default), a Chrome window opens. Advise the user to complete any manual verification if prompted. The script waits up to 90 seconds.
- After the first successful pass, cookies persist in `chrome_profile/` inside the output directory, making later runs smoother.
- For fully automated scheduled runs, the user should first pass the challenge once manually, then use `--headless`.

### 5. Report Results
Read `result.txt` from the output directory (default: current working directory) and present matched results. Include post date, title, matched actors, link, and **magnet links** when available. Present magnet links directly in the chat response so the user can copy them immediately.

### 6. JavDB Magnet Lookup (optional)

When forum threads lack inline magnets (common for `[BT种子]` torrent attachments), use JavDB to resolve magnets by AV number extracted from the post title:

```bash
python scripts/scan.py --days 3 --javdb --javdb-magnets --fetch-magnets
python scripts/javdb_lookup.py SSIS-589 --magnets --best
```

Flags:
- `--javdb` — add release date and JavDB title
- `--javdb-magnets` — fetch ranked magnets from JavDB (merged with forum magnets when both are used)
- `--javdb-best` — keep only the best magnet (prefers cnsub, then HD, then size)
- `--javdb-cnsub` / `--javdb-hd` — filter JavDB magnets

### JavDB login (optional)

Most lookups work anonymously. To use a personal account (collections, VIP content):

```bash
python scripts/javdb_login.py login              # interactive
python scripts/javdb_login.py login -u USER -p PASS
python scripts/javdb_login.py status --check
python scripts/javdb_login.py logout
```

Token is saved to `javdb_auth.json` in the skill directory (gitignored). After login, `javdb_lookup.py` and `scan.py --javdb*` pick up the saved token automatically.

Optional env: `JAVDB_HOST`, `JAVDB_TOKEN`, `JAVDB_AUTH_FILE`, `JAVDB_DEVICE_UUID`.

### 7. Cnsub-First Collect + PikPak (recommended workflow)

When the user wants **Chinese-subtitled magnets** from forum posts and automatic PikPak download:

**Policy (in order):**
1. Forum title indicates cnsub (中字/字幕/中文…) and thread has magnets → use forum magnet
2. Else look up the AV number on JavDB for a cnsub magnet
3. Else fall back to any forum magnet
4. Submit selected magnets to PikPak folder **My Pack**

**One command (API fallback):**
```bash
export PIKPAK_TOKEN="your-token"
python scripts/scan.py --days 3 --cnsub-priority --pikpak --pikpak-folder "My Pack"
```

**With actor list or keyword:**
```bash
python scripts/scan.py --actors 佐々木さき --days 3 --cnsub-priority --pikpak
python scripts/scan.py --keyword 流出 --max-pages 10 --cnsub-priority --pikpak
```

**Agent + PikPak MCP (preferred when MCP is connected):**
1. Run scan with `--cnsub-priority` (no `--pikpak` flag)
2. Read `last_result.json`; for each item use `selected_magnet` (fallback: first `magnets[]`)
3. Call PikPak MCP `add_link` for each magnet; resolve **My Pack** folder id with `ls` at root and pass as `parent`

If MCP is unavailable, use `--pikpak` or `python scripts/pikpak_download.py` after the scan.

Result fields: `selected_magnet`, `magnet_source` (`forum_cnsub` | `javdb_cnsub` | `forum_fallback`).

### 8. PikPak Download (optional)
If PikPak MCP is configured (see `.cursor/mcp.json` and [reference.md](reference.md)), use the `add_link` tool to submit magnet links. Default target folder is **My Pack** — resolve its folder ID with `ls` at root and pass it as `parent`.

If MCP is unavailable, fall back to:
```bash
export PIKPAK_TOKEN="your-token"
python scripts/pikpak_download.py
```

## Output Files
- `result.txt` — Human-readable report (overwritten each run)
- `last_result.json` — Structured data for downstream use
- `screenshots/` — Debug screenshots if errors occur
- `chrome_profile/` — Persistent browser session (do not delete)

## Additional Resources
- For installation, Task Scheduler setup, and detailed parameter reference, see [reference.md](reference.md)
