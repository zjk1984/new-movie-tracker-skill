# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from jellyfin_nfo import (  # noqa: E402
    build_movie_nfo_xml,
    canonical_av_number,
    extract_actress_names,
    extract_cover_url,
    localize_scrape_metadata_zh,
    merge_scrape_metadata,
    metadata_sidecar_names,
    nfo_display_title,
    validate_nfo_xml,
)

class SidecarNamingTests(unittest.TestCase):
    def test_flat_root_sidecars_by_av_number(self):
        names = metadata_sidecar_names("ssis-001")
        self.assertEqual(names["nfo"], "SSIS-001.nfo")
        self.assertEqual(names["poster"], "SSIS-001-poster.jpg")

    def test_fanart_optional(self):
        names = metadata_sidecar_names("MIDV-671", include_fanart=True)
        self.assertEqual(names["fanart"], "MIDV-671-fanart.jpg")

    def test_canonical_av_number(self):
        self.assertEqual(canonical_av_number("  pred-899 "), "PRED-899")


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


class LocalizeMetadataTests(unittest.TestCase):
    @patch("title_translate.translate_ja_to_zh", return_value="中文标题")
    @patch("title_translate.has_japanese", return_value=True)
    def test_localize_title_keeps_originaltitle(self, _has_ja, _translate):
        meta = {"title": "日本語タイトル", "plot": "中文简介", "tags": []}
        out = localize_scrape_metadata_zh(meta)
        self.assertEqual(out["title"], "中文标题")
        self.assertEqual(out["originaltitle"], "日本語タイトル")


class NfoTitleTests(unittest.TestCase):
    def test_display_title_prefixes_number(self):
        self.assertEqual(
            nfo_display_title({"number": "SSIS-001", "title": "测试标题"}),
            "SSIS-001 测试标题",
        )

    def test_display_title_keeps_existing_number(self):
        self.assertEqual(
            nfo_display_title({"number": "SSIS-001", "title": "SSIS-001 测试"}),
            "SSIS-001 测试",
        )


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
        self.assertIn("<title>MIDV-671 测试标题</title>", xml)
        self.assertIn("<plot>一段中文简介。</plot>", xml)
        self.assertIn("<premiered>2023-05-06</premiered>", xml)
        self.assertIn("<year>2023</year>", xml)
        self.assertIn("<name>演员甲</name>", xml)
        self.assertIn('<uniqueid type="jav"', xml)
        self.assertIn("MIDV-671", xml)


if __name__ == "__main__":
    unittest.main()
