# -*- coding: utf-8
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from scan_delta import (  # noqa: E402
    apply_scan_dedup,
    filter_new_download_items,
    filter_new_matched,
    item_dedup_keys,
    rotate_scan_snapshot,
)


class ScanDeltaTests(unittest.TestCase):
    def test_item_dedup_keys_href_and_av(self):
        item = {
            "href": "thread-1.html",
            "title": "[有码] HMN-900 标题",
            "av_number": "HMN-900",
        }
        keys = item_dedup_keys(item)
        self.assertIn("href:thread-1.html", keys)
        self.assertIn("av:HMN-900", keys)

    def test_filter_new_matched_removes_repeat_av(self):
        previous = [{"href": "thread-1.html", "av_number": "HMN-900", "title": "A"}]
        current = [
            {"href": "thread-1.html", "av_number": "HMN-900", "title": "A"},
            {"href": "thread-2.html", "av_number": "MIDA-753", "title": "B"},
        ]
        new_items, repeat = filter_new_matched(current, previous)
        self.assertEqual(repeat, 1)
        self.assertEqual(len(new_items), 1)
        self.assertEqual(new_items[0]["av_number"], "MIDA-753")

    def test_rotate_and_apply_scan_dedup(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            last = out / "last_result.json"
            payload = {
                "scan_time": "2026-09-14T09:00:00+08:00",
                "matched": [
                    {"href": "t1", "av_number": "HMN-900", "title": "old"},
                    {"href": "t2", "av_number": "MIDA-753", "title": "new"},
                ],
            }
            last.write_text(json.dumps(payload), encoding="utf-8")
            self.assertTrue(rotate_scan_snapshot(out))

            scan_stats = {
                "scan_time": payload["scan_time"],
                "matched": [
                    {"href": "t1", "av_number": "HMN-900", "title": "old"},
                    {"href": "t3", "av_number": "SNOS-270", "title": "fresh"},
                ],
                "matched_total": 2,
            }
            download_report = {
                "succeeded": [
                    {"href": "t1", "name": "HMN-900", "uri": "magnet:?xt=urn:btih:111"},
                    {"href": "t3", "name": "SNOS-270", "uri": "magnet:?xt=urn:btih:222"},
                ],
                "failed": [],
                "ok": 2,
                "failed_count": 0,
                "total": 2,
            }
            stats, report = apply_scan_dedup(scan_stats, download_report, output_dir=out)
            self.assertEqual(stats["matched_repeat"], 1)
            self.assertEqual(stats["matched_total"], 1)
            self.assertEqual(stats["matched"][0]["av_number"], "SNOS-270")
            self.assertEqual(len(report["succeeded"]), 1)
            self.assertEqual(report["succeeded"][0]["name"], "SNOS-270")

    def test_filter_new_download_items_before_pikpak(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "previous_result.json").write_text(
                json.dumps({
                    "matched": [
                        {"href": "t1", "av_number": "HMN-900", "title": "old"},
                    ],
                }),
                encoding="utf-8",
            )
            items = [
                {
                    "href": "t1",
                    "name": "HMN-900",
                    "title": "old",
                    "uri": "magnet:?xt=urn:btih:111",
                },
                {
                    "href": "t2",
                    "name": "MIDA-753",
                    "title": "new",
                    "uri": "magnet:?xt=urn:btih:222",
                },
            ]
            kept, skipped = filter_new_download_items(items, out)
            self.assertEqual(skipped, 1)
            self.assertEqual(len(kept), 1)
            self.assertEqual(kept[0]["name"], "MIDA-753")

    def test_no_new_matched_clears_download_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            previous = [
                {"href": "t1", "av_number": "HMN-900"},
                {"href": "t2", "av_number": "MIDA-753"},
            ]
            (out / "previous_result.json").write_text(
                json.dumps({"matched": previous}),
                encoding="utf-8",
            )
            scan_stats = {
                "matched": [{"href": "t1", "av_number": "HMN-900"}],
                "matched_total": 1,
            }
            download_report = {
                "succeeded": [{"href": "t1", "name": "HMN-900", "uri": "magnet:?xt=urn:btih:111"}],
                "failed": [],
                "ok": 1,
                "failed_count": 0,
                "total": 1,
            }
            stats, report = apply_scan_dedup(scan_stats, download_report, output_dir=out)
            self.assertEqual(stats["matched_total"], 0)
            self.assertEqual(report["ok"], 0)
            self.assertEqual(report["succeeded"], [])


if __name__ == "__main__":
    unittest.main()
