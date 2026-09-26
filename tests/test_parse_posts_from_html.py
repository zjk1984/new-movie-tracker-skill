# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))

from scan import parse_posts_from_html  # noqa: E402


class ParsePostsFromHtmlTests(unittest.TestCase):
    def test_desktop_forum142_page_200_fixture(self):
        html = (FIXTURES / "forum-142-200.htm").read_text(encoding="utf-8")
        posts = parse_posts_from_html(html)
        self.assertEqual(len(posts), 3)
        self.assertEqual(posts[0]["href"], "thread-3647981-1-1.html")
        self.assertIn("【BT种子】07/25", posts[0]["title"])
        self.assertEqual(posts[0]["date_text"], "2025-7-25")
        self.assertTrue(all(p["href"].endswith("-1.html") for p in posts))

    def test_mobile_forum142_viewthread_fixture(self):
        html = (FIXTURES / "forum-142-mobile-200.htm").read_text(encoding="utf-8")
        posts = parse_posts_from_html(html)
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0]["href"], "thread-3647981-1-1.html")
        self.assertEqual(posts[1]["href"], "thread-3651447-1-1.html")

    def test_empty_html_returns_no_posts(self):
        self.assertEqual(parse_posts_from_html("<html><body></body></html>"), [])


if __name__ == "__main__":
    unittest.main()
