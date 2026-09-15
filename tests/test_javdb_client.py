# -*- coding: utf-8
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from javdb_client import (  # noqa: E402
    build_query_report,
    ensure_javdb_score_gate,
    extract_tag_names,
    find_excluded_javdb_tag,
    javdb_tags_ok,
)


class JavDBTagTests(unittest.TestCase):
    def test_extract_tag_names_from_detail(self):
        detail = {
            "tags": [
                {"id": 1, "name": "巨乳"},
                {"id": 2, "name": "中出し"},
                {"id": 3, "name": "巨乳"},
            ],
            "maker_name": "S1 NO.1 STYLE",
            "series_name": "测试系列",
        }
        self.assertEqual(extract_tag_names(detail), ["巨乳", "中出し"])

    def test_build_query_report_includes_tags(self):
        info = {
            "query_status": "ok",
            "number": "HMN-900",
            "content_type": "jav_censored",
            "content_type_label": "有码",
            "tags": ["巨乳", "人妻"],
            "tag_labels": "巨乳, 人妻",
            "maker_name": "本中",
            "series_name": "人妻系列",
            "magnet_status": "not_requested",
        }
        report = build_query_report(info)
        self.assertEqual(report["tags"], ["巨乳", "人妻"])
        self.assertEqual(report["tag_labels"], "巨乳, 人妻")
        self.assertEqual(report["maker_name"], "本中")
        self.assertEqual(report["series_name"], "人妻系列")

    def test_find_excluded_javdb_tag(self):
        self.assertEqual(find_excluded_javdb_tag(["巨乳", "多P"]), "多P")
        self.assertEqual(find_excluded_javdb_tag(["恋乳癖"]), "恋乳癖")
        self.assertIsNone(find_excluded_javdb_tag(["巨乳", "人妻"]))
        self.assertIsNone(find_excluded_javdb_tag([]))
        self.assertIsNone(find_excluded_javdb_tag(None))

    def test_javdb_tags_ok_skips_excluded(self):
        item = {
            "content_region": "jav_censored",
            "av_number": "HMN-900",
            "javdb_query": {
                "query_status": "ok",
                "tags": ["巨乳", "业余"],
                "score": 4.5,
            },
        }
        self.assertFalse(javdb_tags_ok(item))

    def test_javdb_tags_ok_allows_clean_tags(self):
        item = {
            "content_region": "jav_censored",
            "av_number": "HMN-900",
            "javdb_query": {
                "query_status": "ok",
                "tags": ["巨乳", "人妻"],
                "score": 4.5,
            },
        }
        self.assertTrue(javdb_tags_ok(item))

    def test_ensure_javdb_score_gate_skips_excluded_tag(self):
        item = {
            "content_region": "jav_censored",
            "av_number": "HMN-900",
            "selected_magnet": "magnet:?xt=urn:btih:abc",
            "javdb_query": {
                "query_status": "ok",
                "number": "HMN-900",
                "tags": ["多P", "巨乳"],
                "score": 4.8,
            },
        }
        self.assertFalse(ensure_javdb_score_gate(item, query_if_missing=False))
        self.assertEqual(item["skip_reason"], "javdb_tag_excluded_多P")
        self.assertNotIn("selected_magnet", item)

    def test_ensure_javdb_score_gate_tag_before_score(self):
        item = {
            "content_region": "jav_censored",
            "av_number": "HMN-900",
            "javdb_query": {
                "query_status": "ok",
                "number": "HMN-900",
                "tags": ["恋乳癖"],
                "score": 2.0,
            },
        }
        self.assertFalse(ensure_javdb_score_gate(item, query_if_missing=False))
        self.assertEqual(item["skip_reason"], "javdb_tag_excluded_恋乳癖")

    def test_ensure_javdb_score_gate_allows_when_no_excluded_tags(self):
        item = {
            "content_region": "jav_censored",
            "av_number": "HMN-900",
            "javdb_query": {
                "query_status": "ok",
                "number": "HMN-900",
                "tags": ["巨乳"],
                "score": 4.5,
            },
        }
        self.assertTrue(ensure_javdb_score_gate(item, query_if_missing=False))


if __name__ == "__main__":
    unittest.main()
