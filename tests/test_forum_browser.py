# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from forum_browser import canonical_thread_href, thread_id_from_href  # noqa: E402
from scan import DEFAULT_FORUM_URLS, dedupe_candidates  # noqa: E402


class CanonicalThreadHrefTests(unittest.TestCase):
    def test_normalizes_page_to_one(self):
        self.assertEqual(
            canonical_thread_href("thread-3762119-1-5.html"),
            "thread-3762119-1-1.html",
        )

    def test_leaves_page_one_unchanged(self):
        self.assertEqual(
            canonical_thread_href("thread-3762119-1-1.html"),
            "thread-3762119-1-1.html",
        )

    def test_thread_id_from_href(self):
        self.assertEqual(thread_id_from_href("thread-3762119-1-5.html"), "3762119")


class DedupeCandidatesTests(unittest.TestCase):
    def test_same_thread_different_pages_deduped(self):
        out = dedupe_candidates([
            {"href": "thread-100-1-2.html", "title": "A"},
            {"href": "thread-100-1-5.html", "title": "A again"},
            {"href": "thread-200-1-1.html", "title": "B"},
        ])
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["href"], "thread-100-1-1.html")
        self.assertEqual(out[1]["href"], "thread-200-1-1.html")

    def test_cross_forum_duplicate_keeps_both_forum_tags(self):
        out = dedupe_candidates([
            {
                "href": "thread-100-1-1.html",
                "title": "A",
                "forum": "https://www.sehuatang.org/forum-142-1.html",
            },
            {
                "href": "thread-100-1-1.html",
                "title": "A",
                "forum": "https://www.sehuatang.org/forum-103-1.html",
            },
        ])
        self.assertEqual(len(out), 1)
        self.assertEqual(
            set(out[0]["forums"]),
            {
                "https://www.sehuatang.org/forum-142-1.html",
                "https://www.sehuatang.org/forum-103-1.html",
            },
        )
        self.assertEqual(
            out[0]["forum"],
            "https://www.sehuatang.org/forum-103-1.html",
        )

    def test_cnsub_forum103_wins_over_forum142_download_link(self):
        out = dedupe_candidates([
            {
                "href": "thread-100-1-1.html",
                "title": "[今日下载链接] ABC-123 9/19",
                "forum": "https://www.sehuatang.org/forum-142-1.html",
            },
            {
                "href": "thread-100-1-1.html",
                "title": "[有码] ABC-123 中文字幕版",
                "forum": "https://www.sehuatang.org/forum-103-1.html",
            },
        ])
        self.assertEqual(len(out), 1)
        self.assertIn("中文字幕", out[0]["title"])
        self.assertEqual(
            out[0]["forum"],
            "https://www.sehuatang.org/forum-103-1.html",
        )
        self.assertEqual(len(out[0]["forums"]), 2)

    def test_cnsub_wins_when_forum103_scanned_first(self):
        out = dedupe_candidates([
            {
                "href": "thread-100-1-1.html",
                "title": "[有码] ABC-123 中文字幕版",
                "forum": "https://www.sehuatang.org/forum-103-1.html",
            },
            {
                "href": "thread-100-1-1.html",
                "title": "[今日下载链接] ABC-123 9/19",
                "forum": "https://www.sehuatang.org/forum-142-1.html",
            },
        ])
        self.assertEqual(len(out), 1)
        self.assertIn("中文字幕", out[0]["title"])
        self.assertEqual(
            out[0]["forum"],
            "https://www.sehuatang.org/forum-103-1.html",
        )

    def test_default_forum_order_puts_103_last(self):
        self.assertIn("forum-103", DEFAULT_FORUM_URLS[-1])
        self.assertEqual(
            [url.split("forum-")[1].split("-")[0] for url in DEFAULT_FORUM_URLS],
            ["2", "95", "142", "37", "103"],
        )


if __name__ == "__main__":
    unittest.main()
