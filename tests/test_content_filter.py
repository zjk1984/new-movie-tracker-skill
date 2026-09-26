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


class DomesticKeywordExclusionTests(unittest.TestCase):
    @staticmethod
    def _ed2k_item(title: str) -> dict:
        return {
            "title": title,
            "ed2k": ["ed2k://|file|sample.mkv|123|ABCDEF0123456789ABCDEF0123456789|/"],
        }

    def test_cepai_excluded_even_with_ed2k(self):
        title = "[国产] 厕拍 某女 115ed2k"
        self.assertTrue(is_domestic_excluded(title))
        self.assertIsNone(domestic_keep_reason(title, has_ed2k=True))
        item = self._ed2k_item(title)
        apply_region_filter(item)
        self.assertEqual(item["content_region"], "domestic_other")
        self.assertFalse(is_downloadable(item))
        self.assertNotIn("selected_ed2k", item)

    def test_heiren_excluded_even_with_ed2k(self):
        title = "[国产] 黑人 泄密 ed2k"
        self.assertTrue(is_domestic_excluded(title))
        self.assertIsNone(domestic_keep_reason(title, has_ed2k=True))

    def test_qingsefenxiang_with_liuchu_kept(self):
        title = "[国产] 情色分享 流出"
        self.assertFalse(is_domestic_excluded(title))
        item = self._ed2k_item(title)
        apply_region_filter(item)
        self.assertEqual(item["content_region"], "domestic_leak")
        self.assertEqual(item.get("domestic_subtype"), "流出")
        self.assertTrue(is_downloadable(item))

    def test_qingsefenxiang_plain_title_kept(self):
        title = "[情色分享] 某女 4K"
        self.assertFalse(is_domestic_excluded(title))
        self.assertEqual(domestic_keep_reason(title), "情色分享")
        item = self._ed2k_item(title)
        apply_region_filter(item)
        self.assertEqual(item["content_region"], "domestic_leak")
        self.assertEqual(item.get("domestic_subtype"), "情色分享")
        self.assertTrue(is_downloadable(item))

    def test_qingsefenxiang_with_115ed2k_kept(self):
        title = "[情色分享] 【自转】【115ED2K】某女 4K"
        self.assertFalse(is_domestic_excluded(title))
        item = self._ed2k_item(title)
        apply_region_filter(item)
        self.assertEqual(item["content_region"], "domestic_leak")
        self.assertEqual(item.get("domestic_subtype"), "情色分享")
        self.assertTrue(is_downloadable(item))

    def test_sipai_still_excluded(self):
        title = "[国产] 私拍 某女"
        self.assertTrue(is_domestic_excluded(title))
        self.assertIsNone(domestic_keep_reason(title))

    def test_clean_domestic_ed2k_still_kept(self):
        title = "[国产] 泄密 115ed2k"
        item = self._ed2k_item(title)
        apply_region_filter(item)
        self.assertEqual(item["content_region"], "domestic_leak")
        self.assertEqual(item.get("domestic_subtype"), "泄密")
        self.assertTrue(is_downloadable(item))

    def test_ed2k_only_subtype_when_no_keyword(self):
        title = "[国产无码] 某女 115ed2k"
        item = self._ed2k_item(title)
        apply_region_filter(item)
        self.assertEqual(item["content_region"], "domestic_leak")
        self.assertEqual(item.get("domestic_subtype"), "ed2k")

    def test_jav_ed2k_classified_as_jav_not_domestic(self):
        title = "[有码] SSIS-123 中文字幕 115ed2k"
        ed2k = "ed2k://|file|SSIS-123.mkv|123|ABCDEF0123456789ABCDEF0123456789|/"
        item = {"title": title, "ed2k": [ed2k]}
        apply_region_filter(item)
        self.assertEqual(item["content_region"], "jav_censored")
        self.assertNotIn("domestic_subtype", item)
        self.assertTrue(is_downloadable(item))

    def test_jav_number_ed2k_body_only_not_domestic(self):
        title = "MIDA-749 4K 115Ed2k"
        item = {
            "title": title,
            "ed2k": ["ed2k://|file|MIDA-749.mkv|123|ABCDEF0123456789ABCDEF0123456789|/"],
        }
        self.assertEqual(classify_region(item), "jav_censored")

    def test_orphan_ed2k_body_not_domestic(self):
        title = "某资源合集"
        item = {
            "title": title,
            "ed2k": ["ed2k://|file|sample.mkv|123|ABCDEF0123456789ABCDEF0123456789|/"],
        }
        apply_region_filter(item)
        self.assertEqual(item["content_region"], "other")
        self.assertFalse(is_downloadable(item))


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

    def test_jiudian_toupai_excluded(self):
        title = "[国产] 酒店偷拍 小少妇"
        self.assertTrue(is_domestic_excluded(title))
        item = {"title": title}
        apply_region_filter(item)
        self.assertEqual(item["content_region"], "domestic_other")
        self.assertFalse(is_downloadable(item))
        self.assertNotIn("domestic_subtype", item)

    def test_zhubo_luzhi_excluded(self):
        title = "[国产] 主播录制 某女 4K"
        self.assertTrue(is_domestic_excluded(title))
        self.assertIsNone(domestic_keep_reason(title))
        item = {"title": title}
        apply_region_filter(item)
        self.assertEqual(item["content_region"], "domestic_other")
        self.assertFalse(is_downloadable(item))
        self.assertNotIn("domestic_subtype", item)

    def test_zhubo_luzhi_excluded_even_with_ed2k(self):
        title = "[国产] 主播录制 115ed2k"
        self.assertTrue(is_domestic_excluded(title))
        self.assertIsNone(domestic_keep_reason(title, has_ed2k=True))
        item = DomesticKeywordExclusionTests._ed2k_item(title)
        apply_region_filter(item)
        self.assertEqual(item["content_region"], "domestic_other")
        self.assertFalse(is_downloadable(item))

    def test_zhubo_luzhi_blocks_other_domestic_keep_tags(self):
        title = "[国产] 泄密 主播录制 某女"
        self.assertTrue(is_domestic_excluded(title))
        self.assertIsNone(domestic_keep_reason(title))
        self.assertEqual(classify_region({"title": title}), "domestic_other")


class DomesticKeepKeywordSubtypeTests(unittest.TestCase):
    @staticmethod
    def _item(title: str) -> dict:
        return {"title": title}

    def test_new_keep_keywords(self):
        cases = [
            ("[国产] 露脸 某女", "露脸"),
            ("[国产] 真实 某女", "真实"),
            ("[国产] 大胸 某女", "大胸"),
            ("[国产] 小少妇", "少妇"),
            ("[国产] 美女 某女", "美女"),
            ("[国产] 学生 某女", "学生"),
            ("[国产] 老师 某女", "老师"),
        ]
        for title, expected_subtype in cases:
            with self.subTest(title=title):
                item = self._item(title)
                apply_region_filter(item)
                self.assertEqual(item["content_region"], "domestic_leak")
                self.assertEqual(item.get("domestic_subtype"), expected_subtype)
                self.assertTrue(is_downloadable(item))

    def test_shunv_selfie_subtype_unchanged(self):
        item = self._item("[国产] 熟女 自拍")
        apply_region_filter(item)
        self.assertEqual(item.get("domestic_subtype"), "熟女自拍")


class DomesticAiDuanjuExclusionTests(unittest.TestCase):
    @staticmethod
    def _ed2k_item(title: str) -> dict:
        return {
            "title": title,
            "ed2k": ["ed2k://|file|sample.mkv|123|ABCDEF0123456789ABCDEF0123456789|/"],
        }

    def test_ai_zhenren_duanju_excluded(self):
        title = "[国产] AI真人短剧 某女 4K"
        self.assertTrue(is_domestic_excluded(title))
        self.assertIsNone(domestic_keep_reason(title))
        item = {"title": title}
        apply_region_filter(item)
        self.assertEqual(item["content_region"], "domestic_other")
        self.assertFalse(is_downloadable(item))
        self.assertNotIn("domestic_subtype", item)

    def test_ai_zhenren_duanju_excluded_even_with_ed2k(self):
        title = "[国产] AI真人短剧 115ed2k"
        self.assertTrue(is_domestic_excluded(title))
        self.assertIsNone(domestic_keep_reason(title, has_ed2k=True))
        item = self._ed2k_item(title)
        apply_region_filter(item)
        self.assertEqual(item["content_region"], "domestic_other")
        self.assertFalse(is_downloadable(item))

    def test_ai_zhenren_duanju_blocks_other_domestic_keep_tags(self):
        title = "[国产] 泄密 AI真人短剧 某女"
        self.assertTrue(is_domestic_excluded(title))
        self.assertIsNone(domestic_keep_reason(title))
        self.assertEqual(classify_region({"title": title}), "domestic_other")

    def test_ai_duanju_excluded(self):
        title = "[国产] AI短剧 某女 1080P"
        self.assertTrue(is_domestic_excluded(title))
        self.assertIsNone(domestic_keep_reason(title))
        item = {"title": title}
        apply_region_filter(item)
        self.assertEqual(item["content_region"], "domestic_other")
        self.assertFalse(is_downloadable(item))
        self.assertNotIn("domestic_subtype", item)

    def test_ai_duanju_excluded_even_with_ed2k(self):
        title = "[国产] AI短剧 115ed2k"
        self.assertTrue(is_domestic_excluded(title))
        self.assertIsNone(domestic_keep_reason(title, has_ed2k=True))
        item = self._ed2k_item(title)
        apply_region_filter(item)
        self.assertEqual(item["content_region"], "domestic_other")
        self.assertFalse(is_downloadable(item))

    def test_ai_duanju_blocks_other_domestic_keep_tags(self):
        title = "[国产] 泄密 AI短剧 某女"
        self.assertTrue(is_domestic_excluded(title))
        self.assertIsNone(domestic_keep_reason(title))
        self.assertEqual(classify_region({"title": title}), "domestic_other")


if __name__ == "__main__":
    unittest.main()
