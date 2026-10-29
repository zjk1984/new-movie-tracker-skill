# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from jellyfin_nfo import (  # noqa: E402
    build_movie_nfo_xml,
    extract_actress_names,
    extract_cover_url,
    merge_scrape_metadata,
    sidecar_names_for_video,
    validate_nfo_xml,
)


class SidecarNamingTests(unittest.TestCase):
    def test_flat_layout(self):
        names = sidecar_names_for_video("SSIS-001-UC.mp4", subfolder_layout=False)
        self.assertEqual(names["nfo"], "SSIS-001-UC.nfo")
        self.assertEqual(names["poster"], "SSIS-001-UC-poster.jpg")

    def test_subfolder_layout(self):
        names = sidecar_names_for_video("movie.mp4", subfolder_layout=True)
        self.assertEqual(names["nfo"], "movie.nfo")
        self.assertEqual(names["poster"], "poster.jpg")


class MetadataExtractTests(unittest.TestCase):
    def test_merge_and_extract(self):
        lookup = {
            "number": "SSIS-001",
            "title": "lookup title",
            "release_date": "2024-01-02",
            "javdb_id": "abc123",
            "tags": ["TagA"],
            "score": 4.5,
        }
        detail = {
            "title": "中文标题",
            "description": "剧情简介",
            "cover_url": "https://img.example/cover.jpg",
            "actresses": [{"name": "山田花", "name_zh": "山田花"}],
        }
        meta = merge_scrape_metadata(lookup, detail)
        self.assertEqual(meta["title"], "中文标题")
        self.assertEqual(meta["plot"], "剧情简介")
        self.assertEqual(meta["actresses"], ["山田花"])
        self.assertEqual(extract_cover_url(detail), "https://img.example/cover.jpg")
        self.assertEqual(extract_actress_names(detail), ["山田花"])


class NfoXmlTests(unittest.TestCase):
    def test_build_movie_nfo_contains_core_fields(self):
        meta = {
            "number": "MIDV-671",
            "title": "测试标题",
            "plot": "一段中文简介。",
            "release_date": "2023-05-06",
            "actresses": ["演员甲", "演员乙"],
            "tags": ["标签一"],
            "maker_name": "Maker",
            "score": 4.2,
            "javdb_id": "xyz",
        }
        xml = build_movie_nfo_xml(meta)
        validate_nfo_xml(xml)
        self.assertIn('<?xml version', xml)
        self.assertIn("<title>测试标题</title>", xml)
        self.assertIn("<plot>一段中文简介。</plot>", xml)
        self.assertIn("<premiered>2023-05-06</premiered>", xml)
        self.assertIn("<year>2023</year>", xml)
        self.assertIn("<name>演员甲</name>", xml)
        self.assertIn('<uniqueid type="jav"', xml)
        self.assertIn("MIDV-671", xml)


if __name__ == "__main__":
    unittest.main()
