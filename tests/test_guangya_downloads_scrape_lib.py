# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from guangya_downloads_jav_scrape_lib import (  # noqa: E402
    iter_guangya_jav_video_files,
    nfo_xml_title_japanese,
)
from pikpak_downloads_jav_scrape_lib import group_videos_by_av  # noqa: E402


class GuangYaJavIterTests(unittest.TestCase):
    @patch("guangya_downloads_jav_scrape_lib.walk_guangya_tree")
    def test_yields_jav_videos_only(self, mock_walk):
        mock_walk.return_value = [
            {"type": "file", "name": "SSIS-001-C.mp4", "id": "v1", "parent_id": "p1"},
            {"type": "file", "name": "readme.txt", "id": "t1", "parent_id": "p1"},
            {"type": "directory", "name": "nested", "id": "d1"},
        ]
        rows = list(iter_guangya_jav_video_files("downloads-id", pseudo_as_jav=False))
        self.assertEqual(len(rows), 1)
        row, parent = rows[0]
        self.assertEqual(row["name"], "SSIS-001-C.mp4")
        self.assertEqual(parent, "p1")

    def test_group_guangya_videos_by_av(self):
        videos = [
            ({"name": "JUR-832-U.mp4", "id": "a"}, "root"),
            ({"name": "javkok.com@JUR-832.mp4", "id": "b"}, "nested"),
        ]
        groups = group_videos_by_av(videos, pseudo_as_jav=True)
        self.assertIn("JUR-832", groups)
        self.assertEqual(len(groups["JUR-832"]), 2)


class NfoRetranslateTests(unittest.TestCase):
    def test_nfo_xml_title_japanese_detects_kana(self):
        xml = """<?xml version="1.0" encoding="utf-8"?>
<movie><title>ADN-767 限界集落の村</title></movie>"""
        self.assertTrue(nfo_xml_title_japanese(xml))

    def test_nfo_xml_title_chinese_only_false(self):
        xml = """<?xml version="1.0" encoding="utf-8"?>
<movie><title>ADN-767 边界村落</title></movie>"""
        self.assertFalse(nfo_xml_title_japanese(xml))


if __name__ == "__main__":
    unittest.main()
