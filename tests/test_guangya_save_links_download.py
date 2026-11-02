# -*- coding: utf-8
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from guangya_save_links_download import (  # noqa: E402
    _inventory_avs_for_skip,
    build_av_magnet_queue,
    load_already_on_save_avs,
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

    def test_builds_from_records_uses_selected_magnet(self) -> None:
        report = {
            "records": [
                {
                    "name": "n1",
                    "av_number": "SSIS-1",
                    "links": ["magnet:?xt=urn:btih:111", "magnet:?xt=urn:btih:222"],
                    "selected_magnet": "magnet:?xt=urn:btih:111",
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


class SkipInventoryTests(unittest.TestCase):
    def test_inventory_skip_includes_sidecar_and_any(self) -> None:
        payload = {
            "av_numbers": ["V-1"],
            "sidecar_only_av": ["N-1", "N-2"],
            "av_any_on_save": ["A-1", "A-2"],
        }
        self.assertEqual(_inventory_avs_for_skip(payload), ["A-1", "A-2"])
        payload2 = {"av_numbers": ["V-1"], "sidecar_only_av": ["N-1"]}
        self.assertEqual(set(_inventory_avs_for_skip(payload2)), {"V-1", "N-1"})

    def test_load_already_on_save_merges_state(self) -> None:
        state = {"av_numbers": {"S-1": {"uri": "magnet:x"}}}
        found = load_already_on_save_avs(state=state, merge_path=Path("/nonexistent"))
        self.assertIn("S-1", found)


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
            already_on_save=set(),
        )
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["av_number"], "B-1")
        self.assertEqual(next_idx, 2)
        self.assertEqual(stats["skipped_state"], 1)

    def test_skips_sidecar_only_on_save(self) -> None:
        queue = [
            {"uri": "magnet:?xt=urn:btih:a", "av_number": "A-1"},
            {"uri": "magnet:?xt=urn:btih:b", "av_number": "B-1"},
        ]
        pending, next_idx, stats = select_pending_rows(
            queue,
            {"av_numbers": {}, "uris": {}},
            start_index=0,
            limit=10,
            already_on_save={"A-1"},
        )
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["av_number"], "B-1")
        self.assertEqual(stats["skipped_already_on_save"], 1)


if __name__ == "__main__":
    unittest.main()
