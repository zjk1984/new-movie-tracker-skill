# Feishu setup for CNBeta RSS

This project sends CNBeta news updates to Feishu using a **custom bot webhook**. Credentials stay in environment variables or a local `.env.local` file (gitignored).

## 1. Create a Feishu custom bot webhook

1. Open the target Feishu group chat.
2. Go to **Settings → Bots → Add bot → Custom bot**.
3. Set a name (for example `CNBeta RSS`) and create the bot.
4. Copy the webhook URL. It looks like:
   `https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
5. If you enabled **Sign verification**, copy the signing secret as well.

## 2. Configure environment variables

Copy `.env.local.example` to `.env.local` and fill in:

| Variable | Required | Description |
|----------|----------|-------------|
| `FEISHU_WEBHOOK_URL` | Yes | Custom bot webhook URL |
| `FEISHU_WEBHOOK_SECRET` | No | Signing secret when webhook sign verification is enabled |

Optional RSS settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `CNBETA_RSS_FEEDS` | `https://rss.cnbeta.com.tw` | Comma-separated feed URLs |
| `CNBETA_RSS_MAX_ITEMS` | `10` | Max new items per run |
| `CNBETA_RSS_STATE_PATH` | `data/cnbeta_rss_state.json` | Seen-item state file |
| `CNBETA_RSS_VERIFY_SSL` | `auto` | Set `false` if SSL verification fails for the RSS host |

Example `.env.local`:

```bash
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-token
FEISHU_WEBHOOK_SECRET=
CNBETA_RSS_MAX_ITEMS=10
```

Do **not** commit `.env.local` or real webhook URLs to git.

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

## 4. Run the aggregator

Fetch and parse only (no Feishu, no state update):

```bash
python scripts/cnbeta_rss.py --fetch-only
```

Preview the message without sending:

```bash
python scripts/cnbeta_rss.py --dry-run --reset-state
```

Send new items to Feishu:

```bash
python scripts/cnbeta_rss.py
```

Use plain text instead of an interactive card:

```bash
python scripts/cnbeta_rss.py --text
```

## 5. Schedule periodic runs

Example cron (every hour):

```bash
0 * * * * cd /path/to/repo && /usr/bin/python3 scripts/cnbeta_rss.py >> logs/cnbeta_rss.log 2>&1
```

The script stores seen article links in `data/cnbeta_rss_state.json` so repeat runs only notify on new items.

## Troubleshooting

- **`missing FEISHU_WEBHOOK_URL`**: export the webhook URL or add it to `.env.local`.
- **Webhook returns sign error**: set `FEISHU_WEBHOOK_SECRET` to match the bot signing secret.
- **SSL errors fetching RSS**: set `CNBETA_RSS_VERIFY_SSL=false`. The script also retries once without verification when the default verify path fails.
