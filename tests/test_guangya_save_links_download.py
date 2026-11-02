# -*- coding: utf-8
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from guangya_save_links_download import (  # noqa: E402
    build_unique_magnet_queue,
    select_pending_rows,
    state_has_uri,
)


class UniqueQueueTests(unittest.TestCase):
    def test_dedupes_by_uri_and_btih(self) -> None:
        report = {
            "entries": [
                {"url": "magnet:?xt=urn:btih:aaa", "av_number": "ABC-001"},
                {"url": "magnet:?xt=urn:btih:aaa", "av_number": "ABC-001"},
                {"url": "magnet:?xt=urn:btih:bbb", "av_number": "ABC-002"},
            ],
        }
        queue = build_unique_magnet_queue(report)
        self.assertEqual(len(queue), 2)
        self.assertEqual(queue[0]["uri"], "magnet:?xt=urn:btih:aaa")

    def test_builds_from_records(self) -> None:
        report = {
            "records": [
                {
                    "name": "n1",
                    "av_number": "SSIS-1",
                    "links": ["magnet:?xt=urn:btih:111", "magnet:?xt=urn:btih:222"],
                },
            ],
        }
        queue = build_unique_magnet_queue(report)
        self.assertEqual(len(queue), 2)


class SelectPendingTests(unittest.TestCase):
    def test_skips_state_and_respects_limit(self) -> None:
        queue = [
            {"uri": "magnet:?xt=urn:btih:a", "av_number": "A"},
            {"uri": "magnet:?xt=urn:btih:b", "av_number": "B"},
            {"uri": "magnet:?xt=urn:btih:c", "av_number": "C"},
        ]
        state = {"uris": {"btih:A": {"uri": queue[0]["uri"]}}}
        self.assertTrue(state_has_uri(state, queue[0]["uri"]))
        pending, next_idx, stats = select_pending_rows(
            queue,
            state,
            start_index=0,
            limit=1,
        )
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["uri"], queue[1]["uri"])
        self.assertEqual(next_idx, 2)
        self.assertEqual(stats["skipped_state"], 1)


if __name__ == "__main__":
    unittest.main()
