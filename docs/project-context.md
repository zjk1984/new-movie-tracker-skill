# Multi-source RSS → Feishu aggregator

## Purpose

A Python script fetches curated RSS feeds across eight categories (Chinese/English tech, politics & economics, finance, AI, insights) and pushes new items to a Feishu group. Foreign-language titles and summaries are translated to Simplified Chinese before Feishu push and markdown archive. The entrypoint remains `scripts/cnbeta_rss.py` for backward compatibility with existing cron wrappers.

## Data flow

```mermaid
flowchart LR
  JSON[scripts/rss_sources.json] --> Fetch[scripts/cnbeta_rss.py]
  RSS[RSS / Atom feeds] --> Fetch
  Fetch --> Parse[Parse items + source category]
  Prev[update/*.md or backup/*.md latest] --> Dedupe[Dedupe by URL/guid + state]
  State[data/cnbeta_rss_state.json] --> Dedupe
  Parse --> Canonical[Canonical URL cross-source dedup]
  Canonical --> Window[Filter last N days]
  Window --> Dedupe
  Dedupe --> Limit[Per-category + total caps]
  Limit --> Enrich[Optional trafilatura excerpt per source]
  Enrich --> Translate[Translate non-Chinese titles/summaries]
  Translate --> Update[update/YYYYMMDD-HHMMSS.md]
  Translate --> Feishu[Feishu app bot or webhook]
  Update --> Backup[update/backup/]
```

1. **Load** feeds from `scripts/rss_sources.json` (or legacy `RSS_FEEDS` / `CNBETA_RSS_FEEDS` override).
2. **Filter** sources by `RSS_ENABLED_CATEGORIES` when set.
3. **Fetch** each feed (RSS 2.0 or Atom). Per-source outcomes (`success` / `empty` / `failure` / `timeout`) are logged, included in run JSON (`fetch_report`), appended to `data/cnbeta_rss.log`, and shown in Feishu card footers when present.
4. **Parse** title, link, publish time, summary, and assign `source_category` + `source_name`.
5. **Canonicalize** article URLs (strip `utm_*`, `fbclid`, `gclid`, etc.) and merge duplicates across feeds before lookback filtering.
6. **Filter** to articles published within the last `RSS_LOOKBACK_DAYS` (default **2**). Older entries are ignored even if unseen — no backlog backfill.
7. **Dedupe** in-window items against `data/cnbeta_rss_state.json` and the latest `update/*.md` (or `update/backup/*.md` when `update/` is empty), matching both raw links and canonical URLs.
8. **Limit** to `RSS_MAX_ITEMS_PER_CATEGORY` (default **7**) per category and `RSS_MAX_ITEMS` (default **50**) total per run.
9. **Enrich** (optional, per feed) short RSS summaries via `trafilatura` when `"enrich": true` in `rss_sources.json` — 8s timeout per item, graceful fallback on failure.
10. **Translate** foreign titles/summaries to Simplified Chinese via `scripts/rss_translate.py` (OpenAI-compatible API when `OPENAI_API_KEY` is set; otherwise `deep-translator`). Chinese text is detected by CJK ratio and skipped. Original title/link are preserved; Feishu cards and markdown show **中文标题/摘要** as primary text with originals alongside when different.
11. **Send** grouped by category to Feishu as an interactive card (or plain text). Batches of **10+** items (or when `FEISHU_COLLAPSIBLE=1`) use Feishu Card JSON 2.0 collapsible panels; smaller batches keep the compact flat card. If nothing qualifies, log `no new RSS items`, skip Feishu, and do not write markdown.
12. **Archive** each non-empty batch to `update/YYYYMMDD-HHMMSS.md` with `<!-- category: ... -->` tags; move the previous file to `update/backup/`.

## Categories

| Key | Label | Example sources |
|-----|-------|-----------------|
| `tech_cn` | 中文科技 | CNBeta, IT之家, Solidot, 少数派, 36氪快讯 |
| `tech_en` | 英文科技 | TechCrunch, The Verge, Ars Technica, HN |
| `politics_econ_cn` | 国内政治经济 | 新华网, FT中文, BBC中文, 联合早报 |
| `politics_econ_intl` | 国际政治经济 | BBC World, Guardian, NYT, FT |
| `finance_cn` | 国内财经 | 华尔街见闻, 第一财经, 同花顺 7×24, Investing.com 中文 |
| `finance_intl` | 国际财经 | Bloomberg, FT Markets, CNBC, MarketWatch, WSJ, BBC Business, Yahoo Finance |
| `ai` | AI | 量子位, MIT TR, OpenAI, Google AI, DeepMind |
| `insights` | 热点洞察 | HN 100+, Product Hunt, Lobsters, Techmeme |

Broken or paywalled feeds are listed under `disabled_feeds` in `scripts/rss_sources.json` with RSSHub fallback notes where applicable.

## Feishu delivery

Two auth modes are supported (auto-detected):

| Mode | Mechanism |
|------|-----------|
| App bot | Tenant access token → `im/v1/messages` (via `scripts/feishu_notify.py`) |
| Webhook | Custom bot webhook POST |

Messages and markdown snapshots group items under category headings (e.g. **【中文科技】**).

See [feishu-setup.md](./feishu-setup.md) for credentials and scheduling.

## Configuration

Core entrypoint:

```bash
python scripts/cnbeta_rss.py
python scripts/cnbeta_rss.py --list-sources
python scripts/cnbeta_rss.py --ping-feishu
```

Legacy single-feed mode (ignores JSON catalog):

```bash
CNBETA_RSS_FEEDS=https://rss.cnbeta.com.tw python scripts/cnbeta_rss.py
```

Feishu credentials live in `.env.local` (see [feishu-setup.md](./feishu-setup.md)). The Python script loads them via `scripts/env_utils.py`; no extra export is needed in cron.

## Scheduled runs

Install with the shared cron helper (same 07:00 / 13:00 / 20:00 Beijing slots as `daily_run`):

```bash
./scripts/setup_cron.sh
```

Wrapper: `scripts/cnbeta_rss.sh` → log `data/cnbeta_rss.log`, crontab marker `# new-movie-tracker-cnbeta`.

## Repository layout

| Path | Role |
|------|------|
| `scripts/cnbeta_rss.py` | Multi-source fetch, parse, canonical dedup, enrich, translate, notify |
| `scripts/rss_translate.py` | Language detection + batch translation to 中文 |
| `scripts/rss_sources.json` | Curated feed catalog by category |
| `scripts/feishu_notify.py` | Shared Feishu app bot client |
| `scripts/env_utils.py` | Shared `.env.local` loader |
| `update/` | Per-run markdown news snapshots (`YYYYMMDD-HHMMSS.md`); gitignored local runtime artifacts — only `.gitkeep` is tracked |
| `update/backup/` | Previous update files archived after each run; gitignored (`update/backup/*.md`) |
| `data/cnbeta_rss_state.json` | Runtime state (gitignored via `data/`) |
| `docs/feishu-setup.md` | Feishu app + webhook + cron configuration |
| `tests/test_cnbeta_rss.py` | RSS parsing, limits, dedup, translation hook, and message tests |
| `tests/test_rss_translate.py` | Translation detection, batching, and bilingual output tests |

`update/*.md` files are created when the aggregator runs locally (or on cron); they are not committed. After `git clone`, expect empty `update/` directories until the first successful run.

## Translation

| Variable | Default | Purpose |
|----------|---------|---------|
| `RSS_TRANSLATE` | `1` | Set `0` to disable translation |
| `OPENAI_API_KEY` | — | Preferred translator (uses `OPENAI_BASE_URL`, `OPENAI_MODEL`) |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Compatible API base |
| `OPENAI_MODEL` | `gpt-4o-mini` | Chat model for batch JSON translations |
| `RSS_TRANSLATE_BATCH_SIZE` | `10` | Strings per API call |
| `RSS_TRANSLATE_CHINESE_THRESHOLD` | `0.35` | CJK ratio above which text is treated as Chinese |

When `OPENAI_API_KEY` is unset, the aggregator falls back to `deep-translator` (Google Translate). Translations are cached in `data/rss_translate_cache.json` (gitignored).

## Horizon-inspired options

| Variable / config | Default | Purpose |
|-------------------|---------|---------|
| `FEISHU_COLLAPSIBLE` | auto | `1` force collapsible Card 2.0 panels; `0` force compact card |
| `FEISHU_COLLAPSIBLE_THRESHOLD` | `10` | Auto-switch to collapsible layout when item count ≥ threshold |
| `"enrich": true` in `rss_sources.json` | off | Fetch page excerpt via `trafilatura` when RSS summary &lt; 80 chars |
| Run JSON `fetch_report` | — | Per-feed `{id, status, item_count, error?}` after each run |

## Cron integration

Scheduled runs use `scripts/cnbeta_rss.sh` (see [PR #66](https://github.com/zjk1984/new-movie-tracker-skill/pull/66)) at **07:00, 13:00, 20:00** Asia/Shanghai alongside the movie tracker. That PR is pending merge; the multi-source aggregator works with manual runs and the same wrapper once cron is installed.

The aggregator reuses the Feishu app client from forum scanner scripts but is otherwise independent of `scan.py`.
