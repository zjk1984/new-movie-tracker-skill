# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from scan import dedupe_candidates  # noqa: E402
from scan_phases import scrape_two_phase, staging_dir  # noqa: E402


class DedupeCandidatesTests(unittest.TestCase):
    def test_dedupe_by_href(self):
        items = [
            {"href": "thread-1.html", "title": "A"},
            {"href": "thread-1.html", "title": "A dup"},
            {"href": "thread-2.html", "title": "B"},
        ]
        out = dedupe_candidates(items)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["href"], "thread-1.html")
        self.assertEqual(out[1]["href"], "thread-2.html")


class StagingDirTests(unittest.TestCase):
    def test_staging_dir_under_output(self):
        out = Path("/tmp/test-scan-out")
        self.assertEqual(staging_dir(out), out / "scan_staging")


class ScrapeTwoPhaseRoutingTests(unittest.TestCase):
    @patch("scan_phases.save_scan_results")
    @patch("scan_phases.bootstrap_storage_state")
    @patch("scan_phases._send_feishu_start")
    @patch("scan_phases.find_chrome", return_value="/usr/bin/chromium")
    @patch("scan_phases.prepare_scrape_setup")
    @patch("scan_phases.ThreadPoolExecutor")
    @patch("scan_phases.sync_playwright")
    def test_phase1_aggregates_forum_results(
        self,
        mock_playwright,
        mock_executor,
        mock_prepare,
        _chrome,
        _feishu,
        mock_bootstrap,
        mock_save,
    ):
        from scan import ForumListResult, MatchContext
        from datetime import datetime

        today = datetime(2026, 9, 15)
        match_ctx = MatchContext(
            keywords=[],
            match_names=set(),
            match_index={},
            since=None,
            until=None,
            cutoff=today,
            today=today,
            all_posts=True,
            no_date_filter=False,
        )
        mock_prepare.return_value = (
            set(),
            set(),
            None,
            match_ctx,
            today,
            today,
            None,
            None,
        )
        mock_bootstrap.return_value = Path("/tmp/state.json")

        r1 = ForumListResult(
            "https://example.org/forum-2-1.html",
            [{"href": "t1.html", "title": "One", "forum": "https://example.org/forum-2-1.html"}],
            30,
            1,
        )
        r2 = ForumListResult(
            "https://example.org/forum-95-1.html",
            [{"href": "t2.html", "title": "Two", "forum": "https://example.org/forum-95-1.html"}],
            27,
            1,
        )

        from concurrent.futures import Future

        class FakePool:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def submit(self, fn, *args, **kwargs):
                fut: Future = Future()
                fut.set_result(fn(*args, **kwargs))
                return fut

        mock_executor.side_effect = FakePool

        browser = MagicMock()
        context = MagicMock()
        page = MagicMock()
        context.new_page.return_value = page
        browser.new_context.return_value = context
        pw = MagicMock()
        pw.chromium.launch.return_value = browser
        mock_playwright.return_value.__enter__.return_value = pw

        args = MagicMock()
        args.output_dir = "/tmp/scan-test-out"
        args.urls = [
            "https://example.org/forum-2-1.html",
            "https://example.org/forum-95-1.html",
        ]
        args.headless = True
        args.fetch_magnets = True
        args.list_workers = 2
        args.fetch_workers = 2
        args.feishu_progress = False

        with patch("scan_phases._list_forum_worker", side_effect=[r1, r2]):
            with patch("scan_phases._enrich_worker", side_effect=lambda item, *a: item):
                scrape_two_phase(args)

        mock_save.assert_called_once()
        saved = mock_save.call_args[0][2]
        self.assertEqual(len(saved), 2)
        self.assertEqual(mock_save.call_args[1]["total_posts"], 57)
        self.assertEqual(mock_save.call_args[1]["total_pages_scanned"], 2)


if __name__ == "__main__":
    unittest.main()
