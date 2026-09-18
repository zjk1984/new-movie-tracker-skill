# Feishu setup for CNBeta RSS

CNBeta news updates can be sent to Feishu using **either** a tenant app bot (recommended) or a custom bot webhook. Credentials stay in environment variables or a local `.env.local` file (gitignored).

## Choose an auth mode

| Mode | When to use | Required variables |
|------|-------------|------------------|
| **App bot** (default when app creds are set) | Enterprise app with IM permissions | `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_RECEIVE_ID` |
| **Webhook** | Simple group custom bot | `FEISHU_WEBHOOK_URL` |

Auto-detection order:

1. If `FEISHU_APP_ID` and `FEISHU_APP_SECRET` are set → **app mode**
2. Else if `FEISHU_WEBHOOK_URL` is set → **webhook mode**
3. Override with `FEISHU_AUTH_MODE=app` or `FEISHU_AUTH_MODE=webhook`

---

## Option A: App bot (tenant access token)

### 1. Create a Feishu app

1. Open [Feishu Open Platform](https://open.feishu.cn/app) → **Create enterprise app**.
2. Note the **App ID** and **App Secret** (Credentials page).
3. Enable **Bot** capability under App Features.
4. Add **im:message** and **im:message:send_as_bot** permissions (or broader IM scope as needed).
5. Publish / install the app to your tenant.
6. Add the app bot to the target group chat.

### 2. Get the target chat ID

The aggregator needs a receive target for app-mode sends.

**Group chat (`chat_id`, most common)**

1. Add your app bot to the group.
2. In Feishu Open Platform → your app → **API Debugger** (or use the IM API):
   - Call `GET /open-apis/im/v1/chats` with a tenant access token to list chats the bot joined, **or**
   - Open the group in Feishu desktop → group settings → copy the chat link; the `chat_id` often appears in developer tools / bot onboarding docs.
3. Set `FEISHU_RECEIVE_ID` to the `chat_id` value (usually starts with `oc_`).

**Alternative receive types**

| Variable | Default | Description |
|----------|---------|-------------|
| `FEISHU_RECEIVE_ID` | — | Target chat / user ID |
| `FEISHU_CHAT_ID` | — | Alias for `FEISHU_RECEIVE_ID` |
| `FEISHU_RECEIVE_ID_TYPE` | `chat_id` | `chat_id`, `open_id`, or `user_id` |

### 3. Configure `.env.local`

```bash
FEISHU_APP_ID=cli_xxxxxxxx
FEISHU_APP_SECRET=xxxxxxxx
FEISHU_RECEIVE_ID=oc_xxxxxxxx
FEISHU_RECEIVE_ID_TYPE=chat_id
CNBETA_RSS_MAX_ITEMS=10
```

### 4. Verify credentials

```bash
python scripts/cnbeta_rss.py --ping-feishu
```

- With only app ID/secret: confirms tenant token fetch; prompts for `FEISHU_RECEIVE_ID` if missing.
- With receive ID set: also sends a test message to the target chat.

---

## Option B: Custom bot webhook

### 1. Create a webhook bot

1. Open the target Feishu group chat.
2. Go to **Settings → Bots → Add bot → Custom bot**.
3. Copy the webhook URL:
   `https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
4. If **Sign verification** is enabled, copy the signing secret.

### 2. Configure `.env.local`

```bash
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-token
FEISHU_WEBHOOK_SECRET=
FEISHU_AUTH_MODE=webhook
```

Force webhook mode when app credentials are also present:

```bash
FEISHU_AUTH_MODE=webhook
```

### 3. Verify

```bash
python scripts/cnbeta_rss.py --ping-feishu
```

---

## RSS settings (both modes)

| Variable | Default | Description |
|----------|---------|-------------|
| `CNBETA_RSS_FEEDS` | `https://rss.cnbeta.com.tw` | Comma-separated feed URLs |
| `CNBETA_RSS_MAX_ITEMS` | `10` | Max new items per run |
| `CNBETA_RSS_STATE_PATH` | `data/cnbeta_rss_state.json` | Seen-item state file |
| `CNBETA_RSS_VERIFY_SSL` | `auto` | Set `false` if SSL verification fails for the RSS host |

Do **not** commit `.env.local` or real credentials to git.

## Install and run

```bash
pip install -r requirements.txt
```

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

Plain text instead of interactive card:

```bash
python scripts/cnbeta_rss.py --text
```

## Schedule periodic runs

```bash
0 * * * * cd /path/to/repo && /usr/bin/python3 scripts/cnbeta_rss.py >> logs/cnbeta_rss.log 2>&1
```

Seen article links are stored in `data/cnbeta_rss_state.json` so repeat runs only notify on new items.

## Troubleshooting

| Error | Fix |
|-------|-----|
| `no Feishu credentials configured` | Set app creds or webhook URL (see above) |
| `missing FEISHU_RECEIVE_ID` | Add bot to group; set `FEISHU_RECEIVE_ID` / `FEISHU_CHAT_ID` |
| `feishu token error` | Check app ID/secret; ensure app is published |
| `feishu send failed` | Confirm bot is in the group and IM permissions are granted |
| Webhook sign error | Set `FEISHU_WEBHOOK_SECRET` |
| SSL errors fetching RSS | Set `CNBETA_RSS_VERIFY_SSL=false` |
