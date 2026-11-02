# -*- coding: utf-8
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from guangya_save_magnet_pick import pick_best_magnet_uri  # noqa: E402
from guangya_save_links_download import (  # noqa: E402
    build_av_magnet_queue,
    select_pending_rows,
)


class MagnetPickTests(unittest.TestCase):
    def test_uc_beats_c(self) -> None:
        links = [
            "magnet:?xt=urn:btih:cccc&dn=FOO-1-C",
            "magnet:?xt=urn:btih:uuuu&dn=FOO-1-UC",
        ]
        uri, meta = pick_best_magnet_uri(links, name_hint="[x]FOO-1")
        self.assertIn("uuuu", uri)
        self.assertEqual(meta["tier_label"], "UC")

    def test_c_beats_plain(self) -> None:
        links = [
            "magnet:?xt=urn:btih:plain&dn=BAR-2",
            "magnet:?xt=urn:btih:ccc&dn=BAR-2-C",
        ]
        uri, meta = pick_best_magnet_uri(links, name_hint="nfo")
        self.assertIn("ccc", uri)
        self.assertEqual(meta["tier_label"], "C")


class AvQueueSkipTests(unittest.TestCase):
    def test_skips_av_already_on_save(self) -> None:
        report = {
            "records": [
                {"av_number": "SSIS-1", "links": ["magnet:?xt=urn:btih:111"], "selected_magnet": "magnet:?xt=urn:btih:111"},
                {"av_number": "SSIS-2", "links": ["magnet:?xt=urn:btih:222"], "selected_magnet": "magnet:?xt=urn:btih:222"},
            ],
        }
        queue = build_av_magnet_queue(report)
        self.assertEqual(len(queue), 2)
        pending, next_idx, stats = select_pending_rows(
            queue,
            {"uris": {}, "av_numbers": {}},
            start_index=0,
            limit=10,
            already_on_save={"SSIS-1"},
        )
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["av_number"], "SSIS-2")
        self.assertEqual(stats["skipped_already_on_save"], 1)
        self.assertEqual(next_idx, 2)


if __name__ == "__main__":
    unittest.main()
