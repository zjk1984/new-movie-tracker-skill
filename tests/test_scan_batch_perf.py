# -*- coding: utf-8
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from scan import (  # noqa: E402
    enrich_matched_post,
    try_gate_before_thread_fetch,
    use_two_phase_scan,
)


class UseTwoPhaseScanTests(unittest.TestCase):
    def test_multi_forum_enables_two_phase(self):
        args = SimpleNamespace(
            serial=False,
            two_phase=True,
            urls=["a", "b"],
            parallel_enrich=False,
            batch_mode=False,
        )
        self.assertTrue(use_two_phase_scan(args))

    def test_single_forum_batch_mode_enables_two_phase(self):
        args = SimpleNamespace(
            serial=False,
            two_phase=True,
            urls=["a"],
            parallel_enrich=False,
            batch_mode=True,
        )
        self.assertTrue(use_two_phase_scan(args))

    def test_single_forum_without_parallel_stays_serial(self):
        args = SimpleNamespace(
            serial=False,
            two_phase=True,
            urls=["a"],
            parallel_enrich=False,
            batch_mode=False,
        )
        self.assertFalse(use_two_phase_scan(args))

    def test_serial_disables_two_phase(self):
        args = SimpleNamespace(
            serial=True,
            two_phase=True,
            urls=["a", "b"],
            parallel_enrich=True,
            batch_mode=True,
        )
        self.assertFalse(use_two_phase_scan(args))


class GateBeforeFetchTests(unittest.TestCase):
    def _args(self, **overrides):
        base = dict(
            gate_before_fetch=True,
            region_filter=True,
            javdb_query=True,
            batch_mode=True,
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    @patch("javdb_client.ensure_javdb_score_gate", return_value=False)
    @patch("javdb_client.attach_javdb_query")
    def test_skips_thread_when_gate_fails(self, mock_attach, mock_gate):
        item = {
            "title": "[无码] IPX-518 絲襪美腿女獄警",
            "href": "thread-1.html",
            "forum": "https://example.org/forum-37-1.html",
        }
        mock_gate.side_effect = lambda it, _client: (
            it.update({"skip_reason": "javdb_score_low_3.00"}) or False
        )
        allowed = try_gate_before_thread_fetch(item, MagicMock(), self._args())
        self.assertFalse(allowed)
        self.assertTrue(item.get("_pre_gate_failed"))
        mock_attach.assert_called_once()
        self.assertFalse(mock_attach.call_args.kwargs.get("fetch_magnets", True))

    @patch("javdb_client.ensure_javdb_score_gate", return_value=True)
    @patch("javdb_client.attach_javdb_query")
    def test_allows_when_no_title_number(self, mock_attach, mock_gate):
        item = {
            "title": "[亚洲无码] 【BT种子】09/20 老行家❤5部精選字幕FHD解密版❤",
            "href": "thread-2.html",
        }
        allowed = try_gate_before_thread_fetch(item, MagicMock(), self._args())
        self.assertTrue(allowed)
        mock_attach.assert_not_called()
        mock_gate.assert_not_called()

    @patch("scan.apply_item_filters")
    @patch("magnet_select.maybe_javdb_magnet_fallback", return_value=False)
    @patch("scan.try_gate_before_thread_fetch", return_value=True)
    @patch("scan.extract_thread_links")
    @patch("magnet_select.apply_selection", return_value=False)
    def test_enrich_uses_javdb_client_for_selection(
        self,
        mock_apply,
        mock_extract,
        mock_gate,
        mock_fallback,
        _mock_filters,
    ):
        mock_extract.return_value = {
            "magnets": [],
            "ed2k": [],
            "pikpak_sha": [],
            "hash_entries": [],
        }
        item = {
            "title": "[有码] ROE-556 测试",
            "href": "thread-4.html",
            "forum": "https://example.org/forum-37-1.html",
        }
        client = MagicMock()
        args = self._args(fetch_magnets=True, cnsub_priority=False)
        enrich_matched_post(MagicMock(), item, args, client)
        mock_apply.assert_called_once_with(item, client)
        self.assertEqual(item.get("av_number"), "ROE-556")
        self.assertGreaterEqual(mock_fallback.call_count, 1)

    @patch("scan.extract_thread_links")
    @patch("javdb_client.ensure_javdb_score_gate", return_value=False)
    @patch("javdb_client.attach_javdb_query")
    def test_enrich_skips_thread_fetch_on_gate_fail(
        self,
        mock_attach,
        mock_gate,
        mock_extract,
    ):
        item = {
            "title": "[无码] STARS-999 测试标题",
            "href": "thread-3.html",
            "forum": "https://example.org/forum-37-1.html",
        }
        mock_gate.side_effect = lambda it, _client: (
            it.update({"skip_reason": "javdb_watched_low_12"}) or False
        )
        args = self._args(fetch_magnets=True, cnsub_priority=True)
        page = MagicMock()
        out = enrich_matched_post(page, item, args, MagicMock())
        mock_extract.assert_not_called()
        self.assertEqual(out["magnets"], [])
        self.assertEqual(out.get("skip_reason"), "javdb_watched_low_12")


class AttachJavdbGateLookupTests(unittest.TestCase):
    @patch("javdb_client.JavDBClient.lookup")
    def test_attach_javdb_query_gate_uses_no_magnets(self, mock_lookup):
        from javdb_client import JavDBClient, attach_javdb_query

        mock_lookup.return_value = {
            "number": "IPX-518",
            "score": 4.5,
            "query_status": "ok",
        }
        client = JavDBClient()
        item = {"title": "IPX-518 test"}
        attach_javdb_query(item, client, fetch_magnets=False)
        mock_lookup.assert_called_once_with("IPX-518", fetch_magnets=False, best_only=True)


if __name__ == "__main__":
    unittest.main()
