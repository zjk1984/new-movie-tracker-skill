# -*- coding: utf-8
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from javdb_client import build_query_report, extract_tag_names  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
