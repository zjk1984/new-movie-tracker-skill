# -*- coding: utf-8
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from feishu_notify import (  # noqa: E402
    build_pikpak_done_card,
    build_scan_done_card,
    build_scan_summary_card,
)


class FeishuMilestoneCardTests(unittest.TestCase):
    def test_build_scan_done_card_has_header(self):
        card = build_scan_done_card(
            {
                "forums": {"forum-37 无码": 300},
                "matched_total": 300,
                "downloadable": 200,
                "with_link": 180,
                "without_link": 20,
                "link_totals": {"magnet": 50, "ed2k": 0, "bt": 0},
                "posts_with": {"magnet": 40, "ed2k": 0, "bt": 0},
            },
            run_label="custom",
        )
        self.assertEqual(card["header"]["title"]["content"], "✅ 扫描完成")

    def test_build_pikpak_done_card_shows_counts(self):
        card = build_pikpak_done_card(
            {"ok": 221, "failed_count": 0, "total": 221},
            run_label="custom",
        )
        body = card["elements"][0]["text"]["content"]
        self.assertIn("221", body)
        self.assertEqual(card["header"]["title"]["content"], "✅ PikPak 提交完成")

    def test_build_scan_summary_card_shows_javdb_tags(self):
        card = build_scan_summary_card(
            {
                "scan_time": "2026-09-15T12:00:00+08:00",
                "forums": {"forum-142 有码": 1},
                "matched_total": 1,
                "downloadable": 1,
                "with_link": 1,
                "without_link": 0,
                "link_totals": {"magnet": 1, "ed2k": 0, "bt": 0},
                "posts_with": {"magnet": 1, "ed2k": 0, "bt": 0},
                "matched": [
                    {
                        "content_region": "jav_censored",
                        "av_number": "HMN-900",
                        "javdb_query": {
                            "query_status": "ok",
                            "number": "HMN-900",
                            "score": 4.25,
                            "release_date": "2026-03-15",
                            "reviews_count": 1234,
                            "tags": ["巨乳", "中出し"],
                            "tag_labels": "巨乳, 中出し",
                        },
                    },
                ],
            },
            {"ok": 1, "failed_count": 0, "total": 1, "succeeded": [], "failed": []},
        )
        body = card["elements"][0]["text"]["content"]
        self.assertIn("**JavDB 标签**", body)
        self.assertIn("**HMN-900**", body)
        self.assertIn("2026-03-15", body)
        self.assertIn("1234人评", body)
        self.assertIn("巨乳", body)
        self.assertIn("中出し", body)

    def test_build_scan_summary_card_omits_tags_when_absent(self):
        card = build_scan_summary_card(
            {
                "scan_time": "2026-09-15T12:00:00+08:00",
                "forums": {},
                "matched_total": 1,
                "downloadable": 1,
                "with_link": 1,
                "without_link": 0,
                "link_totals": {"magnet": 1, "ed2k": 0, "bt": 0},
                "posts_with": {"magnet": 1, "ed2k": 0, "bt": 0},
                "matched": [
                    {
                        "content_region": "jav_censored",
                        "javdb_query": {"query_status": "ok", "number": "ABC-123"},
                    },
                ],
            },
            {"ok": 0, "failed_count": 0, "total": 0, "succeeded": [], "failed": []},
        )
        body = card["elements"][0]["text"]["content"]
        self.assertNotIn("**JavDB 标签**", body)


if __name__ == "__main__":
    unittest.main()
