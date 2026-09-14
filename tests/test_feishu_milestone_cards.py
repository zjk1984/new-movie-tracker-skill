# -*- coding: utf-8
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from feishu_notify import build_pikpak_done_card, build_scan_done_card  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
