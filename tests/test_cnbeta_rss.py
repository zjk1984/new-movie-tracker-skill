# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from cnbeta_rss import (  # noqa: E402
    NewsItem,
    build_interactive_card,
    build_text_message,
    parse_feed,
    resolve_auth_mode,
    select_new_items,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cnbeta_sample.rss"


class CnbetaRssTests(unittest.TestCase):
    def test_parse_feed_reads_items(self):
        xml_text = FIXTURE.read_text(encoding="utf-8")
        items = parse_feed(xml_text, feed_url="https://rss.cnbeta.com.tw")
        self.assertGreaterEqual(len(items), 100)
        first = items[0]
        self.assertTrue(first.title)
        self.assertIn("cnbeta.com.tw", first.link)
        self.assertEqual(first.category, "tech")

    def test_select_new_items_skips_seen(self):
        items = [
            NewsItem(
                item_id="a",
                title="A",
                link="https://example.com/a",
                published="2026-09-18T10:00:00+00:00",
                category="tech",
                summary="",
                feed_url="https://rss.cnbeta.com.tw",
            ),
            NewsItem(
                item_id="b",
                title="B",
                link="https://example.com/b",
                published="2026-09-18T11:00:00+00:00",
                category="tech",
                summary="",
                feed_url="https://rss.cnbeta.com.tw",
            ),
        ]
        fresh = select_new_items(items, {"a"})
        self.assertEqual([item.item_id for item in fresh], ["b"])

    def test_build_messages_include_titles(self):
        item = NewsItem(
            item_id="https://www.cnbeta.com.tw/articles/tech/1.htm",
            title="测试标题",
            link="https://www.cnbeta.com.tw/articles/tech/1.htm",
            published="Fri, 18 Sep 2026 14:17:41 GMT",
            category="tech",
            summary="摘要内容",
            feed_url="https://rss.cnbeta.com.tw",
        )
        text = build_text_message([item], feed_count=1)
        card = build_interactive_card([item], feed_count=1)
        self.assertIn("测试标题", text)
        self.assertIn("测试标题", card["elements"][0]["text"]["content"])

    @patch.dict(
        "os.environ",
        {
            "FEISHU_APP_ID": "cli_test",
            "FEISHU_APP_SECRET": "secret",
            "FEISHU_WEBHOOK_URL": "https://example.com/hook",
        },
        clear=False,
    )
    def test_resolve_auth_mode_prefers_app(self):
        self.assertEqual(resolve_auth_mode(), "app")

    @patch.dict(
        "os.environ",
        {"FEISHU_WEBHOOK_URL": "https://example.com/hook"},
        clear=True,
    )
    def test_resolve_auth_mode_webhook_only(self):
        self.assertEqual(resolve_auth_mode(), "webhook")

    @patch("cnbeta_rss.fetch_feed")
    def test_run_fetch_only(self, mock_fetch):
        mock_fetch.return_value = FIXTURE.read_text(encoding="utf-8")
        from cnbeta_rss import run

        result = run(
            max_items=3,
            dry_run=False,
            fetch_only=True,
            reset_state=True,
            use_card=True,
        )
        self.assertGreaterEqual(result["fetched_total"], 100)
        self.assertLessEqual(result["new_count"], 3)
        self.assertFalse(result["sent"])
        json.dumps(result)


if __name__ == "__main__":
    unittest.main()
