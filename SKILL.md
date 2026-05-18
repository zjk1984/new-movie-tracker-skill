---
name: new-movie-tracker
description: Scan sehuatang.org forums for recent posts and match them against a maintained actor list to identify new releases and extract magnet links. Use when the user asks about actor updates, new movies, sehuatang monitoring, checking favorite actors for new works, forum post filtering, or magnet link extraction.
---

# New Movie Tracker

## Purpose
Monitor sehuatang.org forums for posts published in the last N days, match post titles against an actor list, and report which actors have new releases. Optionally open matched threads to extract magnet links.

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
- `playwright` Python package
- Google Chrome installed

## Workflow

### 1. Verify Environment
Check that `scripts/scan.py` exists in the skill directory. If the user has not installed dependencies, instruct them to run:
```bash
pip install playwright
python -m playwright install
```

### 2. Ensure Actor List Exists
Check `actors.json` in the skill directory. If it is missing or empty, ask the user for their actor list or guide them to initialize it from a directory or direct arguments.

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
Read `result.txt` from the output directory (default: current working directory) and present matched results. Include post date, title, matched actors, link, and magnet links when available.

## Output Files
- `result.txt` — Human-readable report (overwritten each run)
- `last_result.json` — Structured data for downstream use
- `screenshots/` — Debug screenshots if errors occur
- `chrome_profile/` — Persistent browser session (do not delete)

## Additional Resources
- For installation, Task Scheduler setup, and detailed parameter reference, see [reference.md](reference.md)
