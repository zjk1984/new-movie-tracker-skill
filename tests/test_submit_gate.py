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
    collect_gated_downloads,
    filter_download_report,
    iter_download_rows_from_thread,
    iter_ed2k_from_thread,
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

    def test_expands_ed2k_rows(self):
        ed2k = "ed2k://|file|sample.mkv|123|ABCDEF0123456789ABCDEF0123456789|/"
        thread = {
            "href": "thread-ed2k.html",
            "title": "[国产] 泄密 115ed2k",
            "ed2k": [ed2k],
            "selected_ed2k": ed2k,
        }
        rows = iter_ed2k_from_thread(thread)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["link_type"], "ed2k")
        self.assertEqual(rows[0]["uri"], ed2k)

    def test_download_rows_include_ed2k(self):
        ed2k = "ed2k://|file|sample.mkv|123|ABCDEF0123456789ABCDEF0123456789|/"
        thread = {
            "href": "thread-ed2k.html",
            "title": "[国产] 泄密",
            "ed2k": [ed2k],
        }
        rows = iter_download_rows_from_thread(thread)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["link_type"], "ed2k")


class Ed2kDomesticGateTests(unittest.TestCase):
    @patch("submit_gate.ensure_javdb_score_gate", return_value=True)
    def test_excluded_ed2k_thread_skipped(self, _mock_score):
        ed2k = "ed2k://|file|sample.mkv|123|ABCDEF0123456789ABCDEF0123456789|/"
        thread = {
            "href": "thread-cepai.html",
            "title": "[国产] 厕拍 某女",
            "ed2k": [ed2k],
            "selected_ed2k": ed2k,
            "content_region": "domestic_other",
        }
        eligible, skipped = collect_gated_downloads([thread], matched_by_href={})
        self.assertEqual(eligible, [])
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["skip_reason"], "excluded_domestic_other")

    @patch("submit_gate.ensure_javdb_score_gate", return_value=True)
    def test_allowed_domestic_ed2k_thread_eligible(self, _mock_score):
        ed2k = "ed2k://|file|sample.mkv|123|ABCDEF0123456789ABCDEF0123456789|/"
        thread = {
            "href": "thread-leak.html",
            "title": "[国产] 泄密 115ed2k",
            "ed2k": [ed2k],
            "selected_ed2k": ed2k,
        }
        eligible, skipped = collect_gated_downloads([thread], matched_by_href={})
        self.assertEqual(skipped, [])
        self.assertEqual(len(eligible), 1)
        self.assertEqual(eligible[0]["link_type"], "ed2k")
        self.assertEqual(eligible[0]["content_region"], "domestic_leak")
        self.assertEqual(eligible[0]["domestic_subtype"], "泄密")

    @patch("submit_gate.ensure_javdb_score_gate", return_value=True)
    def test_jav_ed2k_thread_uses_javdb_gate(self, mock_score):
        ed2k = "ed2k://|file|SSIS-123.mkv|123|ABCDEF0123456789ABCDEF0123456789|/"
        thread = {
            "href": "thread-jav-ed2k.html",
            "title": "[有码] SSIS-123 115ed2k",
            "ed2k": [ed2k],
            "selected_ed2k": ed2k,
        }
        eligible, skipped = collect_gated_downloads([thread], matched_by_href={})
        self.assertEqual(skipped, [])
        self.assertEqual(len(eligible), 1)
        self.assertEqual(eligible[0]["content_region"], "jav_censored")
        mock_score.assert_called()

    @patch("submit_gate.ensure_javdb_score_gate", return_value=False)
    def test_jav_ed2k_thread_skipped_by_javdb_gate(self, _mock_score):
        ed2k = "ed2k://|file|SSIS-123.mkv|123|ABCDEF0123456789ABCDEF0123456789|/"
        thread = {
            "href": "thread-jav-ed2k.html",
            "title": "[有码] SSIS-123 115ed2k",
            "ed2k": [ed2k],
            "selected_ed2k": ed2k,
        }
        eligible, skipped = collect_gated_downloads([thread], matched_by_href={})
        self.assertEqual(eligible, [])
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["content_region"], "jav_censored")


if __name__ == "__main__":
    unittest.main()
