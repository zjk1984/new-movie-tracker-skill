# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from forum_browser import canonical_thread_href, thread_id_from_href  # noqa: E402
from scan import dedupe_candidates  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
