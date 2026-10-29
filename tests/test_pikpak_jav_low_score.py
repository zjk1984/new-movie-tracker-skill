# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from pikpak_jav_low_score_lib import (  # noqa: E402
    filter_and_sort_low_score_rows,
    filter_low_score_rows,
    row_from_javdb_query,
    sort_low_score_rows,
)
from pikpak_jav_low_score_report_md import (  # noqa: E402
    build_jav_low_score_section,
    format_jav_low_score_table_rows,
)


class JavLowScoreFilterSortTests(unittest.TestCase):
    def _row(self, av: str, score: float | None) -> dict:
        return row_from_javdb_query(
            av,
            {"query_status": "ok", "score": score, "title": av, "tags": []},
            sample_filename=f"{av}.mp4",
        )

    def test_filter_excludes_missing_and_high_scores(self):
        rows = [
            self._row("AAA-001", 3.9),
            self._row("BBB-002", 4.0),
            self._row("CCC-003", None),
            self._row("DDD-004", 2.5),
        ]
        filtered = filter_low_score_rows(rows, max_score_exclusive=4.0)
        avs = [r["av_number"] for r in filtered]
        self.assertEqual(avs, ["AAA-001", "DDD-004"])

    def test_sort_high_to_low_then_av(self):
        rows = [
            self._row("ZZZ-999", 1.0),
            self._row("AAA-001", 3.9),
            self._row("MMM-500", 3.9),
            self._row("BBB-002", 0.5),
        ]
        ordered = sort_low_score_rows(rows)
        self.assertEqual(
            [r["av_number"] for r in ordered],
            ["AAA-001", "MMM-500", "ZZZ-999", "BBB-002"],
        )

    def test_filter_and_sort_combined(self):
        rows = [
            self._row("X-1", 3.0),
            self._row("Y-2", 4.0),
            self._row("Z-3", 3.5),
        ]
        out = filter_and_sort_low_score_rows(rows)
        self.assertEqual([r["av_number"] for r in out], ["Z-3", "X-1"])


class JavLowScoreMarkdownTests(unittest.TestCase):
    def test_table_columns(self):
        rows = [
            {
                "av_number": "ABC-123",
                "score": 3.25,
                "title": "测试标题",
                "tag_labels": "巨乳, 人妻",
                "release_date": "2024-01-01",
                "sample_filename": "ABC-123-C.mp4",
            },
        ]
        table = format_jav_low_score_table_rows(rows)
        self.assertEqual(len(table[0]), 6)
        self.assertEqual(table[0][0], "ABC-123")
        self.assertEqual(table[0][1], "3.25")

    def test_section_includes_threshold(self):
        body = build_jav_low_score_section(
            stats={"jav_folder_av_count": 2, "javdb_queried": 2, "low_score_count": 1},
            rows=[
                {
                    "av_number": "A-1",
                    "score": 1.0,
                    "title": "t",
                    "tag_labels": "",
                    "release_date": "",
                    "sample_filename": "",
                },
            ],
            max_score_exclusive=4.0,
        )
        self.assertIn("评分 < 4", body)
        self.assertIn("A-1", body)


if __name__ == "__main__":
    unittest.main()
