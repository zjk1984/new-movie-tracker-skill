# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from submit_gate import (  # noqa: E402
    build_submit_probe,
    filter_download_report,
    iter_magnets_from_thread,
)
from download_state import empty_state, is_already_submitted, mark_submitted  # noqa: E402


class BuildSubmitProbeTests(unittest.TestCase):
    def test_compilation_row_reclassifies_by_magnet_number(self):
        matched = {
            "thread-3760694-1-2.html": {
                "href": "thread-3760694-1-2.html",
                "title": "[合集] BT 黑客发布",
                "content_region": "other",
            },
        }
        row = {
            "href": "thread-3760694-1-2.html",
            "title": "[合集] BT 黑客发布",
            "name": "MIDA-744 最高すぎた不倫生活",
            "uri": "magnet:?xt=urn:btih:abc&dn=MIDA-744",
        }
        probe = build_submit_probe(row, matched)
        self.assertEqual(probe.get("av_number"), "MIDA-744")
        self.assertIn(probe.get("content_region"), {"jav_censored", "uncensored", "fc2"})

    def test_domestic_hotel_row_stays_domestic(self):
        matched = {
            "thread-3761025-1-1.html": {
                "href": "thread-3761025-1-1.html",
                "title": "[国产] 酒店偷拍",
                "content_region": "domestic_leak",
                "domestic_subtype": "酒店偷拍",
            },
        }
        row = {
            "href": "thread-3761025-1-1.html",
            "name": "6-17酒店偷拍 小少妇",
            "title": "[国产] 酒店偷拍",
            "uri": "magnet:?xt=urn:btih:abc",
        }
        probe = build_submit_probe(row, matched)
        self.assertEqual(probe.get("content_region"), "domestic_leak")
        self.assertEqual(probe.get("domestic_subtype"), "酒店偷拍")


class FilterDownloadReportTests(unittest.TestCase):
    @patch("submit_gate.is_download_row_eligible")
    def test_filters_ineligible_rows(self, mock_eligible):
        mock_eligible.side_effect = [True, False, True]
        report = {
            "ok": 3,
            "failed_count": 0,
            "total": 3,
            "succeeded": [
                {"name": "SAME-221", "href": "t1"},
                {"name": "MIDA-744", "href": "t2"},
                {"name": "HMN-900", "href": "t3"},
            ],
        }
        out = filter_download_report(report, matched=[])
        self.assertEqual(out["ok"], 2)
        self.assertEqual(len(out["succeeded"]), 2)
        self.assertEqual(out["javdb_score_filtered"], 1)


class DownloadStateTests(unittest.TestCase):
    def test_second_btih_same_thread_allowed_by_default(self):
        state = empty_state()
        thread = "thread-3761043-1-1.html"
        first = {
            "href": thread,
            "uri": "magnet:?xt=urn:btih:111",
            "url": "magnet:?xt=urn:btih:111",
        }
        second = {
            "href": thread,
            "uri": "magnet:?xt=urn:btih:222",
            "url": "magnet:?xt=urn:btih:222",
        }
        self.assertFalse(is_already_submitted(first, state))
        mark_submitted(state, [first])
        self.assertTrue(is_already_submitted(first, state))
        self.assertFalse(is_already_submitted(second, state))


class IterMagnetsTests(unittest.TestCase):
    def test_expands_all_magnets(self):
        thread = {
            "href": "thread-1.html",
            "title": "合集",
            "magnets": [
                "magnet:?xt=urn:btih:a&dn=FC2-PPV-123",
                "magnet:?xt=urn:btih:b&dn=FC2-PPV-456",
            ],
        }
        rows = iter_magnets_from_thread(thread)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["av_number"], "FC2-PPV-123")


if __name__ == "__main__":
    unittest.main()
