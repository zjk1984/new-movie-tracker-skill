# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from forum142_batch_run import DEFAULT_FORUM_URL  # noqa: E402
from scan import build_page_url  # noqa: E402


class BuildPageUrlTests(unittest.TestCase):
    def test_forum142_net_page_one_omits_page_param(self):
        self.assertEqual(build_page_url(DEFAULT_FORUM_URL, 1), DEFAULT_FORUM_URL)

    def test_forum142_net_page_200(self):
        self.assertEqual(
            build_page_url(DEFAULT_FORUM_URL, 200),
            "https://www.sehuatang.net/forum.php?mod=forumdisplay&fid=142&mobile=2&page=200",
        )

    def test_forum142_net_page_201(self):
        self.assertEqual(
            build_page_url(DEFAULT_FORUM_URL, 201),
            "https://www.sehuatang.net/forum.php?mod=forumdisplay&fid=142&mobile=2&page=201",
        )

    def test_forum142_net_replaces_existing_page_param(self):
        base = DEFAULT_FORUM_URL + "&page=200"
        self.assertEqual(
            build_page_url(base, 201),
            "https://www.sehuatang.net/forum.php?mod=forumdisplay&fid=142&mobile=2&page=201",
        )

    def test_legacy_org_html_style_still_works(self):
        base = "https://www.sehuatang.org/forum-142-1.html"
        self.assertEqual(build_page_url(base, 1), base)
        self.assertEqual(
            build_page_url(base, 200),
            "https://www.sehuatang.org/forum-142-200.html",
        )


if __name__ == "__main__":
    unittest.main()
