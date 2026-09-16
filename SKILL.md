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
Execute the utility script from the skill directory. Default invocation scans **forum-2 / forum-95 / forum-142** (今日下载链接), **forum-103** (有码), and **forum-37**:
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
Read `result.txt` and `last_result.json` from the output directory. For each **有码/无码** item kept by the content filter, present:

- Post date, title, `content_region` (forum classification), selected magnet + source
- **`javdb_query.summary`** — one-line JavDB lookup result, e.g. `JavDB MIDA-749 [有码] | 发行 2026-08-18 | 磁力 1/16 条可用`
- Copy **selected_magnet** (forum/JavDB policy result), not every raw forum magnet

End with **`javdb_summary`** from JSON when present:

```
javdb_query_summary:
  queried: 40
  with_magnets: 19
  without_magnets: 21
  by_type: 有码 38, 无码 2
```

Explain clearly:
- **有码** = standard censored JAV (`jav_censored`)
- **无码** = Japanese uncensored / 无码破解 (`uncensored`)
- **国产保留** = `[国产无码]` kept as `domestic_leak` — show `domestic_subtype` (泄密 / 流出 / AI增强 / AI短剧 / 熟女自拍 / 酒店偷拍 / ed2k)
- **国产排除** = `domestic_other` — 私拍、伪番号、OnlyFans、探花、推特、剧情等（见下方规则）
- **JavDB 无磁力** = number found on JavDB but magnet list empty (forum magnet may still exist)
- **查询失败** = number not on JavDB or API error

When reporting forum-2 or other domestic-heavy scans, group kept items by `domestic_subtype` and list excluded counts by `skip_reason: excluded_domestic_other`.

### 6. Content Filter — 国产无码规则

Implemented in `scripts/content_filter.py`. Applied by default; disable with `--all-regions`.

#### 识别

标题含 **`[国产无码]`**、`国产无码`、`[国产]` 等标记 → 按**国产无码**处理（优先于普通「无码」关键字，避免误保留）。

主要来源：**forum-2、forum-95、forum-142**（今日下载链接聚合）。

#### 保留（`content_region: domestic_leak`）

标题满足以下**任一**保留条件，且**未命中**下方排除项：

| `domestic_subtype` | 匹配 |
|--------------------|------|
| **泄密** | 含「泄密」或「泄露」 |
| **流出** | 含「流出」（**不含**「未流出」） |
| **AI增强** | 含「AI增强」或「AI 增强」 |
| **AI短剧** | 含「AI短剧」或「AI真人短剧」 |
| **熟女自拍** | 含「熟女」 |
| **酒店偷拍** | 含「酒店偷拍」（含乐橙酒店偷拍等） |
| **ed2k** | 国产帖：标题含 ed2k/115Ed2k/115eD2k 等，或帖内 `ed2k://`（须命中国产上下文，非 blanket domestic） |

保留帖子的 `selected_download` / 磁力会提交 PikPak；JSON 字段 `domestic_subtype` 标明子类。

#### 排除（`content_region: domestic_other`）

以下**一律排除**，即使同时带有 AI增强 / 泄密 等标签：

| 排除原因 | 匹配 |
|----------|------|
| **私拍** | 标题含「私拍」 |
| **厕拍** | 标题含「厕拍」 |
| **黑人** | 标题含「黑人」 |
| **情色分享** | 标题含「情色分享」 |
| **AI增强** | 标题含「AI增强」或「AI 增强」 |
| **伪JAV番号** | 番号前缀 XJX、JDSY、MDSY、MDSR、JDSC、CNXX、RXAJ、TMW、TMG、YCM 等（如 `XJX-380`、`MDSR-0009-1`） |
| **OnlyFans** | OnlyFans、HongKongDoll、Hong Kong Doll、玩偶姐姐 |

此外默认排除的国产内容（无上述保留标签）：探花、推特、OnlyFans 以外网红、剧情工作室、福利姬、Cos、BBC 等 → `domestic_other`。

#### 与日本片的区别

| 类型 | `content_region` | 说明 |
|------|------------------|------|
| 日本有码 | `jav_censored` | MIDA-749、SNOS-270 等标准番号 |
| 日本无码 | `uncensored` | 无码破解、HEYZO 等 |
| 国产保留 | `domestic_leak` | 泄密 / 流出 / AI增强 / AI短剧 / 熟女自拍 / 酒店偷拍 / ed2k（且非排除项） |
| 国产排除 | `domestic_other` | 有磁力但不下载 |

#### 汇报示例

```
国产无码 filter (forum-2 today):
  kept: 8  (AI增强 6, 泄密 2)
  excluded_domestic_other: 19  (私拍 1, 伪番号 4, OnlyFans 1, 探花/推特/剧情 13)
```

引用 `selected_download` + `domestic_subtype`，不要粘贴全部原始磁力列表。被排除的帖子仍保留 `magnets[]` / `hash_entries[]` 供恢复，但不会提交 PikPak。

### 7. JavDB Magnet Lookup (optional)

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

### 8. Cnsub-First Collect + PikPak (recommended workflow)

When the user wants **Chinese-subtitled magnets** from forum posts and automatic PikPak download:

**Content filter (default):** Japanese **有码** + **无码破解** + **国产/ed2k**（泄密/流出/AI短剧/熟女自拍/酒店偷拍/ed2k；排除私拍/厕拍/黑人/情色分享/AI增强/伪番号/OnlyFans）。详见 **§6 国产无码规则**。Western、FC2、素人 JAV 排除。`--all-regions` 关闭全部过滤。

**Download policy (in order):**
1. Forum title indicates cnsub (中字/字幕/中文…) and thread has magnets → use forum magnet
2. Else look up the AV number on JavDB for a cnsub magnet
3. Else fall back to any forum magnet
4. **If the post has no magnet links:** collect from the thread body — `ed2k://`, `PikPak://` feature codes, `filename|size|hash` pipe codes, and BT seed labels **【特征全码】/【哈希校验】/【特徵全碼】** (40-char btih → `magnet:?xt=urn:btih:...`, stored in `hash_entries` + `magnets`)
5. No-magnet fallback order: PikPak SHA → ed2k → JavDB cnsub (when `--cnsub-priority`)
6. Submit `selected_download` (magnet / ed2k / feature code) to PikPak **My Pack** (有码 + 无码 JAV only)

**JavDB download gates (日本有码/无码):** tags → reviews_count → score (≥ 4.0). Reviews threshold by release year (Asia/Shanghai): prior years ≥ 1000, current year ≥ 100. **Exception:** release within the last **7 calendar days** (北京时间) passes even if `reviews_count` is 0 or missing — newly released titles like MXGS-1446 are not blocked while reviews accumulate.

**Save PikPak token once (persisted in skill directory):**
```bash
python scripts/pikpak_login.py login
python scripts/pikpak_login.py status --check
```

Token is saved to `pikpak_auth.json` (gitignored). Scripts pick it up automatically; env `PIKPAK_TOKEN` overrides if set.

**One command (API fallback):**
```bash
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

Result fields: `selected_magnet`, `magnet_source`, `content_region`, `javdb_query` (with `summary`, `content_type_label`, `magnet_status`).

Disable per-item JavDB reporting with `--no-javdb-query`.

### 9. PikPak Download (optional)
If PikPak MCP is configured (see `.cursor/mcp.json` and [reference.md](reference.md)), use the `add_link` tool to submit magnet links. Default target folder is **My Pack** — resolve its folder ID with `ls` at root and pass it as `parent`.

If MCP is unavailable, fall back to:
```bash
python scripts/pikpak_download.py --new-only
python scripts/pikpak_download.py --sha 'PikPak://file.mkv|123456789|GCID40CHARHASH...'
```

**Feature code (特征码):** `PikPak://文件名|字节大小|GCID` — instant cloud add when PikPak already has the file. Forum scans also extract `pikpak_sha`; selection order: magnet → JavDB cnsub → PikPak SHA → ed2k.

### 10. Daily Schedule (07:00 + 13:00 + 20:00 Beijing, incremental download)

Run three times daily at **07:00, 13:00, and 20:00 Asia/Shanghai (北京时间)** to scan recent forum posts and submit **only new magnets** since the last run (tracked in `download_state.json`). Install with `scripts/setup_cron.sh` (Linux) or `scripts/setup_windows_task.ps1` (Windows).

**Linux cron:** `./scripts/setup_cron.sh` installs all three slots. System timezone should be **Asia/Shanghai** so cron wall-clock matches Beijing time. Then run **`sudo service cron restart`** so the daemon reloads the crontab.

**One-time setup**
1. Save PikPak token: `python scripts/pikpak_login.py login` (stored in `pikpak_auth.json`).
2. Pass Cloudflare once: `python scripts/daily_run.py --no-headless` (uses `data/chrome_profile/`).
3. Register the scheduled task (see [reference.md](reference.md)).

**Daily command**
```bash
python scripts/daily_run.py --headless
```

Defaults: scan **forum-2 + forum-95 + forum-142 + forum-103 + forum-37**, `--all-posts`, `--cnsub-priority`, last **2 days**, content filter (日本有码/无码 + 国产泄密/流出/AI增强), PikPak **My Pack**, **new-only** dedup.

Explain results to the user:
- **本次新增** — magnets submitted this run (not in previous `download_state.json`)
- **已跳过** — same thread or same btih already downloaded before
- **无新增** — scan ran but nothing new to submit

### 11. Feishu notifications (optional)

Configure in `.env.local` (see `.env.local.example`):

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_RECEIVE_ID=oc_xxx          # group chat_id — add bot to the group first
FEISHU_RECEIVE_ID_TYPE=chat_id    # or open_id / user_id
```

Verify token: `python scripts/feishu_notify.py ping`

Each run writes a Markdown report under `reports/` (committed to GitHub) with full download fail/success tables. Feishu receives a **scan summary card** with a link to the report.

```bash
python scripts/feishu_notify.py cards --reconstruct
python scripts/feishu_notify.py cards --input data/last_result.json --download-report data/download_report.json
```

`daily_run.py` auto-generates report + Feishu notify when `FEISHU_RECEIVE_ID` is set (use `--no-feishu` to disable).

## Output Files
- `result.txt` — Human-readable report (overwritten each run)
- `last_result.json` — Structured data for downstream use
- `download_state.json` — Submitted magnet/thread history (for incremental runs)
- `pikpak_auth.json` — Saved PikPak token (gitignored)
- `screenshots/` — Debug screenshots if errors occur
- `chrome_profile/` — Persistent browser session (do not delete)

## Additional Resources
- For installation, Task Scheduler setup, and detailed parameter reference, see [reference.md](reference.md)
