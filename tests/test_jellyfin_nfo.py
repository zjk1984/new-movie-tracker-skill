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
    parse_runtime_minutes,
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
            "duration": 118,
        }
        detail = {
            "title": "中文标题",
            "description": "剧情简介",
            "cover_url": "https://img.example/cover.jpg",
            "actresses": [{"name": "山田花", "name_zh": "山田花"}],
            "director_name": "監督A",
        }
        meta = merge_scrape_metadata(lookup, detail)
        self.assertEqual(meta["title"], "中文标题")
        self.assertEqual(meta["plot"], "剧情简介")
        self.assertEqual(meta["actresses"], ["山田花"])
        self.assertEqual(meta["director"], "監督A")
        self.assertEqual(meta["duration"], 118)
        self.assertEqual(meta["genres"], meta["tags"])
        self.assertEqual(extract_cover_url(detail), "https://img.example/cover.jpg")
        self.assertEqual(extract_actress_names(detail), ["山田花"])

    def test_parse_runtime_minutes(self):
        self.assertEqual(parse_runtime_minutes(118), "118")
        self.assertEqual(parse_runtime_minutes("118分"), "118")
        self.assertEqual(parse_runtime_minutes("1:58:00"), "118")


class LocalizeMetadataTests(unittest.TestCase):
    @patch("title_translate.translate_av_metadata_to_zh", side_effect=lambda t: f"ZH:{t}")
    @patch("title_translate.translate_ja_to_zh", side_effect=lambda t: f"JA:{t}")
    @patch(
        "title_translate.has_japanese",
        side_effect=lambda t: any("\u3040" <= c <= "\u30ff" for c in t),
    )
    def test_localize_clears_plot_and_translates_fields(self, _has_ja, _translate_ja, _translate_meta):
        meta = {
            "title": "日本語タイトル",
            "plot": "日本語あらすじ",
            "tags": ["ドラマ", "人妻"],
            "genres": ["ドラマ", "人妻"],
            "maker_name": "アタッカーズ",
            "director": "監督名",
            "actresses": ["山田ハナコ"],
            "originaltitle": "旧标题",
        }
        out = localize_scrape_metadata_zh(meta)
        self.assertEqual(out["title"], "JA:日本語タイトル")
        self.assertEqual(out["plot"], "")
        self.assertEqual(out["maker_name"], "ZH:アタッカーズ")
        self.assertEqual(out["director"], "ZH:監督名")
        self.assertEqual(out["genres"], ["ZH:ドラマ", "ZH:人妻"])
        self.assertIn("ZH:アタッカーズ", out["tags"])
        self.assertEqual(out["actresses"], ["JA:山田ハナコ"])
        self.assertNotIn("originaltitle", out)


class NfoTitleTests(unittest.TestCase):
    def test_display_title_includes_number_title_actress(self):
        self.assertEqual(
            nfo_display_title({
                "number": "ADN-148",
                "title": "不忠的等级关系",
                "actresses": ["松下纱荣子"],
            }),
            "ADN-148 不忠的等级关系 松下纱荣子",
        )

    def test_display_title_strips_duplicate_number_prefix(self):
        self.assertEqual(
            nfo_display_title({"number": "SSIS-001", "title": "SSIS-001 测试标题"}),
            "SSIS-001 测试标题",
        )


class NfoXmlTests(unittest.TestCase):
    def test_build_movie_nfo_adn148_template_shape(self):
        meta = {
            "number": "ADN-148",
            "title": "不忠的等级关系",
            "release_date": "2017-12-16",
            "duration": 118,
            "director": "佐田正男",
            "actresses": ["松下纱荣子"],
            "genres": ["OL", "剧情", "高清", "中文字幕", "人妻", "单体作品", "巨乳", "独占配信"],
            "tags": ["Attackers", "大人的剧情"],
            "maker_name": "Attackers",
            "dateadded": "2026-07-29 18:59:44",
        }
        xml = build_movie_nfo_xml(meta)
        validate_nfo_xml(xml)
        self.assertIn('<?xml version', xml)
        self.assertRegex(xml, r"<plot\s*/>")
        self.assertIn("<lockdata>false</lockdata>", xml)
        self.assertIn("<dateadded>2026-07-29 18:59:44</dateadded>", xml)
        self.assertIn("<title>ADN-148 不忠的等级关系 松下纱荣子</title>", xml)
        self.assertNotIn("<originaltitle>", xml)
        self.assertIn("<director>佐田正男</director>", xml)
        self.assertIn("<year>2017</year>", xml)
        self.assertIn("<mpaa>JP-18+</mpaa>", xml)
        self.assertIn("<premiered>2017-12-16</premiered>", xml)
        self.assertIn("<releasedate>2017-12-16</releasedate>", xml)
        self.assertIn("<runtime>118</runtime>", xml)
        self.assertIn("<tagline>配信开始日 2017-12-16</tagline>", xml)
        self.assertIn("<genre>OL</genre>", xml)
        self.assertIn("<genre>剧情</genre>", xml)
        self.assertRegex(xml, r"<studio\s*/>")
        self.assertIn("<studio>Attackers</studio>", xml)
        self.assertIn("<metatubeid>JavBus:ADN-148</metatubeid>", xml)
        self.assertIn("<poster>ADN-148-poster.jpg</poster>", xml)
        self.assertIn("<fanart>ADN-148-fanart.jpg</fanart>", xml)
        self.assertIn("<name>松下纱荣子</name>", xml)
        for omitted in ("<sorttitle>", "<uniqueid", "<rating>", "<num>", "fileinfo", "streamdetails"):
            self.assertNotIn(omitted, xml, msg=f"unexpected field {omitted}")


if __name__ == "__main__":
    unittest.main()
