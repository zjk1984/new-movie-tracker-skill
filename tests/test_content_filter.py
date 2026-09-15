# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from content_filter import (  # noqa: E402
    apply_region_filter,
    classify_region,
    domestic_keep_reason,
    is_domestic_excluded,
    is_downloadable,
    title_has_ai_enhanced,
)


class TitleHasAiEnhancedTests(unittest.TestCase):
    def test_matches_compact_form(self):
        self.assertTrue(title_has_ai_enhanced("某女 AI增强 4K"))

    def test_matches_spaced_form(self):
        self.assertTrue(title_has_ai_enhanced("某女 AI 增强 版"))

    def test_no_match_without_marker(self):
        self.assertFalse(title_has_ai_enhanced("国产泄密 某女"))


class DomesticAiEnhancedExclusionTests(unittest.TestCase):
    def test_ai_enhanced_only_not_kept(self):
        self.assertIsNone(domestic_keep_reason("[国产] 某女 AI增强 4K"))
        self.assertTrue(is_domestic_excluded("[国产] 某女 AI增强 4K"))

    def test_ai_enhanced_blocks_other_domestic_keep_tags(self):
        title = "[国产] 泄密 AI增强 某女"
        self.assertIsNone(domestic_keep_reason(title))
        self.assertEqual(classify_region({"title": title}), "domestic_other")

    def test_ai_enhanced_domestic_not_downloadable(self):
        item = {"title": "[国产无码] 某女 AI增强 1080P"}
        apply_region_filter(item)
        self.assertEqual(item["content_region"], "domestic_other")
        self.assertFalse(is_downloadable(item))
        self.assertEqual(item.get("skip_reason"), "excluded_domestic_other")
        self.assertNotIn("domestic_subtype", item)
        self.assertNotIn("selected_magnet", item)

    def test_non_domestic_jav_with_ai_enhanced_unchanged(self):
        title = "SSIS-123 AI增强版 中文字幕"
        item = {"title": title}
        apply_region_filter(item)
        self.assertEqual(item["content_region"], "jav_censored")
        self.assertTrue(is_downloadable(item))
        self.assertNotIn("skip_reason", item)

    def test_domestic_leak_without_ai_enhanced_still_kept(self):
        title = "[国产] 酒店偷拍 小少妇"
        item = {"title": title}
        apply_region_filter(item)
        self.assertEqual(item["content_region"], "domestic_leak")
        self.assertEqual(item.get("domestic_subtype"), "酒店偷拍")
        self.assertTrue(is_downloadable(item))


if __name__ == "__main__":
    unittest.main()
