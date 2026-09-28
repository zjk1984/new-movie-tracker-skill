# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from download_state import (  # noqa: E402
    empty_state,
    filter_new_items,
    is_already_submitted,
    mark_submitted,
)


class AvNumberDedupTests(unittest.TestCase):
    def test_same_av_different_btih_second_blocked_in_batch(self):
        """START-638: two forum threads, same av_number, different btih → one submit."""
        state = empty_state()
        first = {
            "av_number": "START-638",
            "href": "thread-3781056-1-1.html",
            "uri": "magnet:?xt=urn:btih:C8B9D289B3C5D6775A98CFA048C26A0B8473E5F9",
            "url": "magnet:?xt=urn:btih:C8B9D289B3C5D6775A98CFA048C26A0B8473E5F9",
        }
        second = {
            "av_number": "START-638",
            "href": "thread-3780755-1-1.html",
            "uri": "magnet:?xt=urn:btih:5B2BDE75103FE1F674E8A52CED1E7CBF4278D7FC",
            "url": "magnet:?xt=urn:btih:5B2BDE75103FE1F674E8A52CED1E7CBF4278D7FC",
        }
        kept = filter_new_items([first, second], state)
        self.assertEqual(kept, [first])
        self.assertEqual(second.get("skip_reason"), "duplicate_av_number")

    def test_same_av_blocked_after_mark_submitted(self):
        state = empty_state()
        first = {
            "av_number": "START-638",
            "uri": "magnet:?xt=urn:btih:AAA",
            "url": "magnet:?xt=urn:btih:AAA",
        }
        mark_submitted(state, [first])
        second = {
            "av_number": "START-638",
            "uri": "magnet:?xt=urn:btih:BBB",
            "url": "magnet:?xt=urn:btih:BBB",
        }
        self.assertTrue(is_already_submitted(second, state))
        kept = filter_new_items([second], state)
        self.assertEqual(kept, [])
        self.assertEqual(second.get("skip_reason"), "repeat_av_number")

    def test_batch_prefers_cnsub_magnet_for_same_av(self):
        state = empty_state()
        plain = {
            "av_number": "ABC-123",
            "uri": "magnet:?xt=urn:btih:plain&dn=ABC-123",
            "url": "magnet:?xt=urn:btih:plain&dn=ABC-123",
        }
        cnsub = {
            "av_number": "ABC-123",
            "uri": "magnet:?xt=urn:btih:cnsub&dn=ABC-123.中文字幕",
            "url": "magnet:?xt=urn:btih:cnsub&dn=ABC-123.中文字幕",
        }
        kept = filter_new_items([plain, cnsub], state)
        self.assertEqual(kept, [cnsub])
        self.assertEqual(plain.get("skip_reason"), "duplicate_av_number")

    def test_batch_keeps_first_when_both_non_cnsub(self):
        state = empty_state()
        first = {
            "av_number": "START-634",
            "uri": "magnet:?xt=urn:btih:111",
            "url": "magnet:?xt=urn:btih:111",
        }
        second = {
            "av_number": "START-634",
            "uri": "magnet:?xt=urn:btih:222",
            "url": "magnet:?xt=urn:btih:222",
        }
        kept = filter_new_items([first, second], state)
        self.assertEqual(kept, [first])
        self.assertEqual(second.get("skip_reason"), "duplicate_av_number")

    def test_no_av_number_items_not_deduped(self):
        state = empty_state()
        a = {
            "name": "6-17酒店偷拍",
            "uri": "magnet:?xt=urn:btih:aaa",
            "url": "magnet:?xt=urn:btih:aaa",
        }
        b = {
            "name": "6-18酒店偷拍",
            "uri": "magnet:?xt=urn:btih:bbb",
            "url": "magnet:?xt=urn:btih:bbb",
        }
        kept = filter_new_items([a, b], state)
        self.assertEqual(len(kept), 2)

    def test_mark_submitted_records_av_number(self):
        state = empty_state()
        item = {
            "av_number": "HMN-900",
            "uri": "magnet:?xt=urn:btih:abc",
            "url": "magnet:?xt=urn:btih:abc",
        }
        mark_submitted(state, [item])
        self.assertIn("HMN-900", state["av_numbers"])
        self.assertEqual(state["av_numbers"]["HMN-900"]["name"], "HMN-900")

    def test_repeat_btih_and_hash_skip_reasons(self):
        state = empty_state()
        bt_item = {
            "name": "something_without_av_1",
            "uri": "magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12",
        }
        hash_item = {
            "name": "something_without_av_2",
            "hash": "FEDCBA0987654321FEDCBA0987654321FEDCBA09",
        }
        mark_submitted(state, [bt_item, hash_item])

        dupe_bt = {
            "name": "something_without_av_1_new",
            "uri": "magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12",
        }
        dupe_hash = {
            "name": "something_without_av_2_new",
            "hash": "FEDCBA0987654321FEDCBA0987654321FEDCBA09",
        }
        kept = filter_new_items([dupe_bt, dupe_hash], state)
        self.assertEqual(kept, [])
        self.assertEqual(dupe_bt.get("skip_reason"), "repeat_btih")
        self.assertEqual(dupe_hash.get("skip_reason"), "repeat_hash")

    def test_mark_manual_download(self):
        from download_state import is_already_submitted, mark_manual_download

        state = empty_state()
        mark_manual_download(state, "SSIS-888", title="SSIS-888 手工测试")
        self.assertIn("SSIS-888", state["av_numbers"])
        record = state["av_numbers"]["SSIS-888"]
        self.assertEqual(record["download_method"], "manual")
        self.assertEqual(record["status"], "manual_download")
        self.assertTrue(is_already_submitted({"av_number": "SSIS-888"}, state))

        # Test marking magnet URI
        mag = "magnet:?xt=urn:btih:1111222233334444555566667777888899990000&dn=TEST-001"
        mark_manual_download(state, mag)
        self.assertTrue(is_already_submitted({"uri": mag}, state))
        self.assertIn("TEST-001", state["av_numbers"])


if __name__ == "__main__":
    unittest.main()
