# -*- coding: utf-8
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from javdb_client import (  # noqa: E402
    build_query_report,
    current_beijing_year,
    ensure_javdb_score_gate,
    extract_av_number,
    extract_tag_names,
    find_excluded_javdb_tag,
    javdb_reviews_ok,
    javdb_tags_ok,
    needs_javdb_query,
    parse_release_date_year,
    reviews_threshold_for_year,
)


class AvNumberExtractionTests(unittest.TestCase):
    def test_extract_pred_899_from_title_and_magnet(self):
        self.assertEqual(extract_av_number("PRED-899 美人上司"), "PRED-899")
        self.assertEqual(
            extract_av_number("magnet:?xt=urn:btih:CCC&dn=PRED-899%20美人上司"),
            "PRED-899",
        )

    def test_extract_pred899_without_hyphen_not_matched(self):
        self.assertIsNone(extract_av_number("PRED899"))


class NeedsJavdbQueryTests(unittest.TestCase):
    def test_needs_query_when_thread_query_is_for_other_number(self):
        item = {
            "av_number": "PRED-899",
            "javdb_query": {
                "query_status": "ok",
                "number": "MIDA-783",
                "score": 4.2,
            },
        }
        self.assertTrue(needs_javdb_query(item))

    def test_no_query_needed_when_number_matches(self):
        item = {
            "av_number": "PRED-899",
            "javdb_query": {
                "query_status": "ok",
                "number": "PRED-899",
                "score": 4.34,
            },
        }
        self.assertFalse(needs_javdb_query(item))

    def test_needs_query_when_missing(self):
        item = {"av_number": "PRED-899"}
        self.assertTrue(needs_javdb_query(item))


class JavDBTagTests(unittest.TestCase):
    def test_extract_tag_names_from_detail(self):
        detail = {
            "tags": [
                {"id": 1, "name": "巨乳"},
                {"id": 2, "name": "中出し"},
                {"id": 3, "name": "巨乳"},
            ],
            "maker_name": "S1 NO.1 STYLE",
            "series_name": "测试系列",
        }
        self.assertEqual(extract_tag_names(detail), ["巨乳", "中出し"])

    def test_build_query_report_includes_tags(self):
        info = {
            "query_status": "ok",
            "number": "HMN-900",
            "content_type": "jav_censored",
            "content_type_label": "有码",
            "release_date": "2026-03-01",
            "reviews_count": 1500,
            "tags": ["巨乳", "人妻"],
            "tag_labels": "巨乳, 人妻",
            "maker_name": "本中",
            "series_name": "人妻系列",
            "magnet_status": "not_requested",
        }
        report = build_query_report(info)
        self.assertEqual(report["tags"], ["巨乳", "人妻"])
        self.assertEqual(report["tag_labels"], "巨乳, 人妻")
        self.assertEqual(report["release_date"], "2026-03-01")
        self.assertEqual(report["reviews_count"], 1500)
        self.assertEqual(report["maker_name"], "本中")
        self.assertEqual(report["series_name"], "人妻系列")

    def test_find_excluded_javdb_tag(self):
        self.assertEqual(find_excluded_javdb_tag(["巨乳", "多P"]), "多P")
        self.assertEqual(find_excluded_javdb_tag(["恋乳癖"]), "恋乳癖")
        self.assertEqual(find_excluded_javdb_tag(["淫语", "人妻"]), "淫语")
        self.assertIsNone(find_excluded_javdb_tag(["巨乳", "人妻"]))
        self.assertIsNone(find_excluded_javdb_tag([]))
        self.assertIsNone(find_excluded_javdb_tag(None))

    def test_javdb_tags_ok_skips_excluded(self):
        item = {
            "content_region": "jav_censored",
            "av_number": "HMN-900",
            "javdb_query": {
                "query_status": "ok",
                "tags": ["巨乳", "业余"],
                "score": 4.5,
            },
        }
        self.assertFalse(javdb_tags_ok(item))

    def test_javdb_tags_ok_allows_clean_tags(self):
        item = {
            "content_region": "jav_censored",
            "av_number": "HMN-900",
            "javdb_query": {
                "query_status": "ok",
                "tags": ["巨乳", "人妻"],
                "score": 4.5,
            },
        }
        self.assertTrue(javdb_tags_ok(item))

    def test_ensure_javdb_score_gate_skips_excluded_tag(self):
        item = {
            "content_region": "jav_censored",
            "av_number": "HMN-900",
            "selected_magnet": "magnet:?xt=urn:btih:abc",
            "javdb_query": {
                "query_status": "ok",
                "number": "HMN-900",
                "tags": ["多P", "巨乳"],
                "score": 4.8,
            },
        }
        self.assertFalse(ensure_javdb_score_gate(item, query_if_missing=False))
        self.assertEqual(item["skip_reason"], "javdb_tag_excluded_多P")
        self.assertNotIn("selected_magnet", item)

    def test_ensure_javdb_score_gate_tag_before_score(self):
        item = {
            "content_region": "jav_censored",
            "av_number": "HMN-900",
            "javdb_query": {
                "query_status": "ok",
                "number": "HMN-900",
                "tags": ["恋乳癖"],
                "score": 2.0,
            },
        }
        self.assertFalse(ensure_javdb_score_gate(item, query_if_missing=False))
        self.assertEqual(item["skip_reason"], "javdb_tag_excluded_恋乳癖")

    def test_ensure_javdb_score_gate_allows_when_no_excluded_tags(self):
        item = {
            "content_region": "jav_censored",
            "av_number": "HMN-900",
            "javdb_query": {
                "query_status": "ok",
                "number": "HMN-900",
                "tags": ["巨乳"],
                "release_date": "2026-01-01",
                "reviews_count": 200,
                "score": 4.5,
            },
        }
        self.assertTrue(ensure_javdb_score_gate(item, query_if_missing=False))


class JavDBReviewsGateTests(unittest.TestCase):
    MOCK_YEAR = 2025

    def test_current_beijing_year_delegates_to_beijing_now(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from env_utils import beijing_now

        with patch("env_utils.beijing_now", return_value=datetime(2027, 6, 15, tzinfo=ZoneInfo("Asia/Shanghai"))):
            self.assertEqual(current_beijing_year(), 2027)

    def test_reviews_threshold_uses_runtime_beijing_year(self):
        with patch("javdb_client.current_beijing_year", return_value=self.MOCK_YEAR):
            self.assertEqual(reviews_threshold_for_year(self.MOCK_YEAR - 1), 1000)
            self.assertEqual(reviews_threshold_for_year(self.MOCK_YEAR), 100)

    def test_parse_release_date_year(self):
        self.assertEqual(parse_release_date_year("2025-12-31"), 2025)
        self.assertEqual(parse_release_date_year("2026-01-01"), 2026)
        self.assertIsNone(parse_release_date_year(""))
        self.assertIsNone(parse_release_date_year("invalid"))

    def test_reviews_threshold_for_year(self):
        y = self.MOCK_YEAR
        self.assertEqual(reviews_threshold_for_year(y - 1, current_year=y), 1000)
        self.assertEqual(reviews_threshold_for_year(y, current_year=y), 100)
        self.assertEqual(reviews_threshold_for_year(y + 1, current_year=y), 100)

    def _item(self, *, release_date: str, reviews_count: int, score: float = 4.5):
        return {
            "content_region": "jav_censored",
            "av_number": "HMN-900",
            "javdb_query": {
                "query_status": "ok",
                "number": "HMN-900",
                "tags": ["巨乳"],
                "release_date": release_date,
                "reviews_count": reviews_count,
                "score": score,
            },
        }

    def test_javdb_reviews_ok_prior_year_needs_1000(self):
        y = self.MOCK_YEAR
        with patch("javdb_client.current_beijing_year", return_value=y):
            with self.subTest("below threshold"):
                item = self._item(release_date=f"{y - 1}-06-01", reviews_count=999)
                self.assertFalse(javdb_reviews_ok(item))
            with self.subTest("at threshold"):
                item = self._item(release_date=f"{y - 1}-06-01", reviews_count=1000)
                self.assertTrue(javdb_reviews_ok(item))

    def test_javdb_reviews_ok_current_year_needs_100(self):
        y = self.MOCK_YEAR
        with patch("javdb_client.current_beijing_year", return_value=y):
            with self.subTest("below threshold"):
                item = self._item(release_date=f"{y}-03-01", reviews_count=99)
                self.assertFalse(javdb_reviews_ok(item))
            with self.subTest("at threshold"):
                item = self._item(release_date=f"{y}-03-01", reviews_count=100)
                self.assertTrue(javdb_reviews_ok(item))

    def test_javdb_reviews_ok_year_boundary_dec31_vs_jan1(self):
        y = self.MOCK_YEAR
        with patch("javdb_client.current_beijing_year", return_value=y):
            dec31 = self._item(release_date=f"{y - 1}-12-31", reviews_count=500)
            self.assertFalse(javdb_reviews_ok(dec31))
            jan1 = self._item(release_date=f"{y}-01-01", reviews_count=500)
            self.assertTrue(javdb_reviews_ok(jan1))

    def test_javdb_reviews_ok_missing_fields(self):
        item = {
            "content_region": "jav_censored",
            "javdb_query": {
                "query_status": "ok",
                "release_date": "2026-01-01",
            },
        }
        self.assertFalse(javdb_reviews_ok(item))
        item["javdb_query"] = {
            "query_status": "ok",
            "reviews_count": 200,
        }
        self.assertFalse(javdb_reviews_ok(item))

    def test_ensure_javdb_score_gate_skips_low_reviews(self):
        with patch("javdb_client.current_beijing_year", return_value=self.MOCK_YEAR):
            item = self._item(release_date=f"{self.MOCK_YEAR}-02-01", reviews_count=50)
            item["selected_magnet"] = "magnet:?xt=urn:btih:abc"
            self.assertFalse(ensure_javdb_score_gate(item, query_if_missing=False))
            self.assertEqual(item["skip_reason"], "javdb_reviews_low_50")
            self.assertNotIn("selected_magnet", item)

    def test_ensure_javdb_score_gate_reviews_before_score(self):
        with patch("javdb_client.current_beijing_year", return_value=self.MOCK_YEAR):
            item = self._item(
                release_date=f"{self.MOCK_YEAR - 1}-01-01",
                reviews_count=10,
                score=2.0,
            )
            self.assertFalse(ensure_javdb_score_gate(item, query_if_missing=False))
            self.assertEqual(item["skip_reason"], "javdb_reviews_low_10")

    def test_ensure_javdb_score_gate_allows_high_reviews(self):
        with patch("javdb_client.current_beijing_year", return_value=self.MOCK_YEAR):
            item = self._item(
                release_date=f"{self.MOCK_YEAR - 1}-01-01",
                reviews_count=1200,
            )
            self.assertTrue(ensure_javdb_score_gate(item, query_if_missing=False))


if __name__ == "__main__":
    unittest.main()
