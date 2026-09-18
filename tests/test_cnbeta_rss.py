# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from cnbeta_rss import (  # noqa: E402
    NewsItem,
    build_interactive_card,
    build_text_message,
    build_update_markdown,
    find_latest_update_md,
    parse_feed,
    parse_item_ids_from_update_md,
    resolve_auth_mode,
    resolve_max_items,
    select_new_items,
    write_update_markdown,
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

    def test_resolve_max_items_defaults_to_20(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(resolve_max_items(), 20)

    def test_parse_item_ids_from_update_md(self):
        md = """# CNBeta 新闻更新

<!-- item-id: https://example.com/a -->
1. **[科技]** [A](https://example.com/a)
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-09-18_1500.md"
            path.write_text(md, encoding="utf-8")
            ids = parse_item_ids_from_update_md(path)
        self.assertEqual(ids, {"https://example.com/a"})

    def test_write_update_markdown_archives_previous(self):
        item = NewsItem(
            item_id="https://www.cnbeta.com.tw/articles/tech/2.htm",
            title="新标题",
            link="https://www.cnbeta.com.tw/articles/tech/2.htm",
            published="2026-09-18T12:00:00+00:00",
            category="tech",
            summary="摘要",
            feed_url="https://rss.cnbeta.com.tw",
        )
        previous_content = build_update_markdown(
            [
                NewsItem(
                    item_id="https://www.cnbeta.com.tw/articles/tech/1.htm",
                    title="旧标题",
                    link="https://www.cnbeta.com.tw/articles/tech/1.htm",
                    published="2026-09-18T11:00:00+00:00",
                    category="tech",
                    summary="",
                    feed_url="https://rss.cnbeta.com.tw",
                )
            ],
            previous=None,
            update_dir=Path("update"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            update_dir = Path(tmp) / "update"
            update_dir.mkdir()
            previous = update_dir / "2026-09-18_1400.md"
            previous.write_text(previous_content, encoding="utf-8")

            new_path, archived = write_update_markdown(
                [item],
                update_dir=update_dir,
                previous=previous,
            )
            self.assertIsNotNone(new_path)
            self.assertTrue(new_path.exists())
            self.assertFalse(previous.exists())
            self.assertIsNotNone(archived)
            self.assertTrue(archived.exists())
            self.assertEqual(find_latest_update_md(update_dir), new_path)
            text = new_path.read_text(encoding="utf-8")
            self.assertIn("新标题", text)
            self.assertIn("[2026-09-18_1400.md](backup/2026-09-18_1400.md)", text)

    @patch("cnbeta_rss.fetch_feed")
    def test_run_dedupes_against_previous_update_md(self, mock_fetch):
        mock_fetch.return_value = FIXTURE.read_text(encoding="utf-8")
        from cnbeta_rss import parse_feed, run

        items = parse_feed(mock_fetch.return_value, feed_url="https://rss.cnbeta.com.tw")
        first_id = items[0].item_id
        with tempfile.TemporaryDirectory() as tmp:
            update_dir = Path(tmp) / "update"
            update_dir.mkdir()
            previous = update_dir / "2026-09-18_1400.md"
            previous.write_text(
                build_update_markdown([items[0]], previous=None, update_dir=update_dir),
                encoding="utf-8",
            )
            with patch("cnbeta_rss.resolve_update_dir", return_value=update_dir):
                with patch("cnbeta_rss.resolve_state_path") as mock_state:
                    state_path = Path(tmp) / "state.json"
                    mock_state.return_value = state_path
                    result = run(
                        max_items=20,
                        dry_run=True,
                        fetch_only=False,
                        reset_state=False,
                        use_card=True,
                        skip_update_md=False,
                    )
        self.assertNotIn(first_id, [item["item_id"] for item in result["items"]])


if __name__ == "__main__":
    unittest.main()
