# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from cnbeta_rss import (  # noqa: E402
    NewsItem,
    _format_item_summary,
    _format_item_title,
    build_interactive_card,
    build_update_markdown,
    translate_items_for_output,
)
from rss_translate import (  # noqa: E402
    apply_translations_to_items,
    chinese_ratio,
    is_primarily_chinese,
    translate_batch,
    translate_to_zh,
)


class RssTranslateTests(unittest.TestCase):
    def test_chinese_ratio_detects_english(self):
        self.assertLess(chinese_ratio("Fed raises interest rates again"), 0.2)
        self.assertFalse(is_primarily_chinese("Fed raises interest rates again"))

    def test_chinese_ratio_detects_chinese(self):
        self.assertGreater(chinese_ratio("美联储再次加息"), 0.8)
        self.assertTrue(is_primarily_chinese("美联储再次加息"))

    def test_chinese_mixed_content_skips_translation(self):
        self.assertTrue(is_primarily_chinese("苹果发布新款 iPhone，售价 799 美元"))

    @patch("rss_translate.translate_to_zh")
    def test_translate_batch_uses_deep_translator(self, mock_translate):
        mock_translate.side_effect = lambda text: {
            "Fed raises rates": "美联储加息",
            "Markets wobble": "市场震荡",
        }.get(text, "")
        with patch("rss_translate.TRANSLATE_ENABLED", True):
            with patch("rss_translate._cache", {}):
                with patch("rss_translate._cache_loaded", True):
                    results = translate_batch(
                        ["Fed raises rates", "Markets wobble"],
                    )
        self.assertEqual(results, ["美联储加息", "市场震荡"])
        self.assertEqual(mock_translate.call_count, 2)

    @patch("rss_translate.translate_to_zh")
    def test_translate_batch_skips_chinese(self, mock_translate):
        mock_translate.return_value = "Another English headline zh"
        with patch("rss_translate._cache", {}):
            with patch("rss_translate._cache_loaded", True):
                results = translate_batch(["中文标题", "Another English headline"])
        self.assertEqual(results[0], "中文标题")
        mock_translate.assert_called_once_with("Another English headline")

    @patch("rss_translate.translate_batch")
    def test_apply_translations_to_items_sets_zh_fields(self, mock_batch):
        mock_batch.side_effect = lambda texts: [
            "美联储加息" if t == "Fed hike" else "摘要中文" for t in texts
        ]
        item = NewsItem(
            item_id="1",
            title="Fed hike",
            link="https://example.com/1",
            published="2026-09-18T10:00:00+00:00",
            category="finance",
            summary="Short summary",
            feed_url="https://example.com/feed",
            source_category="finance_intl",
        )
        apply_translations_to_items([item])
        self.assertEqual(item.title_zh, "美联储加息")
        self.assertEqual(item.summary_zh, "摘要中文")

    @patch("rss_translate.apply_translations_to_items")
    def test_translate_items_for_output_delegates(self, mock_apply):
        item = NewsItem(
            item_id="1",
            title="Hello",
            link="https://example.com/1",
            published="2026-09-18T10:00:00+00:00",
            category="tech",
            summary="",
            feed_url="https://example.com/feed",
        )
        mock_apply.return_value = [item]
        result = translate_items_for_output([item])
        mock_apply.assert_called_once()
        self.assertEqual(result, [item])

    def test_format_item_title_shows_bilingual(self):
        item = NewsItem(
            item_id="1",
            title="Fed hike",
            link="https://example.com/1",
            published="2026-09-18T10:00:00+00:00",
            category="finance",
            summary="",
            feed_url="https://example.com/feed",
            title_zh="美联储加息",
        )
        self.assertEqual(_format_item_title(item), "美联储加息（Fed hike）")

    def test_build_messages_use_chinese_title(self):
        item = NewsItem(
            item_id="1",
            title="Fed hike",
            link="https://example.com/1",
            published="2026-09-18T10:00:00+00:00",
            category="finance",
            summary="Markets react",
            feed_url="https://example.com/feed",
            source_category="finance_intl",
            title_zh="美联储加息",
            summary_zh="市场反应剧烈",
        )
        card = build_interactive_card([item], feed_count=1)
        md = build_update_markdown([item], feed_count=1, previous_filename=None)
        content = card["elements"][0]["text"]["content"]
        self.assertIn("美联储加息", content)
        self.assertIn("Fed hike", content)
        self.assertIn("市场反应剧烈", content)
        self.assertIn("- **原标题**: Fed hike", md)
        self.assertIn("美联储加息（Fed hike）", md)

    @patch("rss_translate._translate_with_google")
    @patch("rss_translate._translate_with_mymemory")
    def test_translate_to_zh_falls_back_to_google_on_mymemory_error(
        self,
        mock_mymemory,
        mock_google,
    ):
        mock_mymemory.side_effect = RuntimeError("quota")
        mock_google.return_value = "美联储加息"
        with patch("rss_translate.TRANSLATE_ENABLED", True):
            with patch("rss_translate._cache", {}):
                with patch("rss_translate._cache_loaded", True):
                    with patch("rss_translate._save_disk_cache"):
                        result = translate_to_zh("Fed raises interest rates again")
        self.assertEqual(result, "美联储加息")
        mock_google.assert_called_once()

    @patch("rss_translate._translate_with_google")
    @patch("rss_translate._translate_with_mymemory")
    def test_translate_to_zh_falls_back_to_google_on_empty_mymemory(
        self,
        mock_mymemory,
        mock_google,
    ):
        mock_mymemory.return_value = ""
        mock_google.return_value = "市场震荡"
        with patch("rss_translate.TRANSLATE_ENABLED", True):
            with patch("rss_translate._cache", {}):
                with patch("rss_translate._cache_loaded", True):
                    with patch("rss_translate._save_disk_cache"):
                        result = translate_to_zh("Markets wobble")
        self.assertEqual(result, "市场震荡")
        mock_google.assert_called_once()


if __name__ == "__main__":
    unittest.main()
