# -*- coding: utf-8
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from guangya_save_links_download import (  # noqa: E402
    build_av_magnet_queue,
    migrate_state,
    select_pending_rows,
    state_has_av,
    state_has_row,
)


class AvQueueTests(unittest.TestCase):
    def test_one_magnet_per_av_first_in_report_order(self) -> None:
        report = {
            "entries": [
                {"url": "magnet:?xt=urn:btih:aaa", "av_number": "ABC-001"},
                {"url": "magnet:?xt=urn:btih:bbb", "av_number": "ABC-001"},
                {"url": "magnet:?xt=urn:btih:ccc", "av_number": "ABC-002"},
            ],
        }
        queue = build_av_magnet_queue(report)
        self.assertEqual(len(queue), 2)
        self.assertEqual(queue[0]["av_number"], "ABC-001")
        self.assertEqual(queue[0]["uri"], "magnet:?xt=urn:btih:aaa")
        self.assertEqual(queue[1]["av_number"], "ABC-002")

    def test_builds_from_records_first_link_only(self) -> None:
        report = {
            "records": [
                {
                    "name": "n1",
                    "av_number": "SSIS-1",
                    "links": ["magnet:?xt=urn:btih:111", "magnet:?xt=urn:btih:222"],
                },
            ],
        }
        queue = build_av_magnet_queue(report)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["uri"], "magnet:?xt=urn:btih:111")

    def test_skips_entries_without_av(self) -> None:
        report = {
            "entries": [
                {"url": "magnet:?xt=urn:btih:aaa", "av_number": ""},
                {"url": "magnet:?xt=urn:btih:bbb", "av_number": "X-1"},
            ],
        }
        queue = build_av_magnet_queue(report)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["av_number"], "X-1")


class StateMigrationTests(unittest.TestCase):
    def test_v1_empty_submissions_resets_cursor(self) -> None:
        old = {
            "schema_version": 1,
            "next_queue_index": 500,
            "queue_unique_count": 16498,
            "uris": {},
        }
        new = migrate_state(old)
        self.assertEqual(new["schema_version"], 2)
        self.assertEqual(new["next_queue_index"], 0)
        self.assertEqual(new["queue_mode"], "one_magnet_per_av")


class SelectPendingTests(unittest.TestCase):
    def test_skips_by_av_and_respects_limit(self) -> None:
        queue = [
            {"uri": "magnet:?xt=urn:btih:a", "av_number": "A-1"},
            {"uri": "magnet:?xt=urn:btih:b", "av_number": "B-1"},
            {"uri": "magnet:?xt=urn:btih:c", "av_number": "C-1"},
        ]
        state = {"av_numbers": {"A-1": {"uri": queue[0]["uri"]}}, "uris": {}}
        self.assertTrue(state_has_av(state, "A-1"))
        self.assertTrue(state_has_row(state, queue[0]))
        pending, next_idx, stats = select_pending_rows(
            queue,
            state,
            start_index=0,
            limit=1,
        )
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["av_number"], "B-1")
        self.assertEqual(next_idx, 2)
        self.assertEqual(stats["skipped_state"], 1)


if __name__ == "__main__":
    unittest.main()
