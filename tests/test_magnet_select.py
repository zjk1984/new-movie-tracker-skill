# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from javdb_client import extract_all_av_numbers  # noqa: E402
from magnet_select import (  # noqa: E402
    apply_selection,
    build_number_downloads,
    magnet_has_cnsub,
    maybe_javdb_magnet_fallback,
    number_from_magnet,
    select_magnet,
)
from pikpak_download import iter_item_downloads  # noqa: E402


class MagnetCnsubTests(unittest.TestCase):
    def test_magnet_has_cnsub_uc_suffix(self):
        mag = "magnet:?xt=urn:btih:abc&dn=ABC-123-UC%20title"
        self.assertTrue(magnet_has_cnsub(mag))

    def test_forum_cnsub_magnet_wins_without_cnsub_title(self):
        item = {
            "title": "[有码] ABC-123 普通版",
            "av_number": "ABC-123",
            "magnets": [
                "magnet:?xt=urn:btih:plain&dn=ABC-123%20no%20sub",
                "magnet:?xt=urn:btih:cnsub&dn=ABC-123-UC%20cnsub",
            ],
        }
        selection = select_magnet(item, javdb_client=None)
        self.assertEqual(selection["source"], "forum_cnsub")
        self.assertIn("cnsub", selection["magnet"])

    def test_javdb_cnsub_wins_over_forum_non_cnsub(self):
        item = {
            "title": "[有码] ABC-123 普通版",
            "av_number": "ABC-123",
            "magnets": [
                "magnet:?xt=urn:btih:plain&dn=ABC-123%20no%20sub",
            ],
        }

        class FakeJavDB:
            def lookup(self, number, *, fetch_magnets=False, cnsub=False, best_only=False):
                self.last_cnsub = cnsub
                if cnsub:
                    return {
                        "magnets": ["magnet:?xt=urn:btih:javdbcnsub"],
                        "javdb_id": "1",
                        "number": number,
                        "title": "t",
                        "release_date": "2026-01-01",
                        "content_type": "jav_censored",
                        "content_type_label": "有码",
                        "has_cnsub": True,
                        "cnsub_magnet_count": 1,
                        "score": 4.5,
                        "reviews_count": 100,
                        "query_status": "ok",
                    }
                return {"magnets": [], "query_status": "ok", "number": number}

        client = FakeJavDB()
        selection = select_magnet(item, javdb_client=client)
        self.assertEqual(selection["source"], "javdb_cnsub")
        self.assertEqual(selection["magnet"], "magnet:?xt=urn:btih:javdbcnsub")
        self.assertTrue(client.last_cnsub)

    def test_forum_non_cnsub_before_javdb_non_cnsub(self):
        item = {
            "title": "[有码] ABC-123",
            "av_number": "ABC-123",
            "magnets": ["magnet:?xt=urn:btih:forum&dn=ABC-123%20plain"],
        }

        class FakeJavDB:
            def lookup(self, number, *, fetch_magnets=False, cnsub=False, best_only=False):
                if cnsub:
                    return {"magnets": [], "query_status": "ok", "number": number}
                return {
                    "magnets": ["magnet:?xt=urn:btih:javdbplain"],
                    "javdb_id": "1",
                    "number": number,
                    "title": "t",
                    "release_date": "2026-01-01",
                    "content_type": "jav_censored",
                    "content_type_label": "有码",
                    "has_cnsub": False,
                    "cnsub_magnet_count": 0,
                    "score": 4.5,
                    "reviews_count": 100,
                    "query_status": "ok",
                }

        selection = select_magnet(item, javdb_client=FakeJavDB())
        self.assertEqual(selection["source"], "forum_fallback")

    def test_maybe_javdb_magnet_fallback_fetches_when_no_forum_links(self):
        item = {
            "title": "[有码] ROE-556 测试标题",
            "magnets": [],
        }

        class FakeJavDB:
            def lookup(self, number, *, fetch_magnets=False, cnsub=False, best_only=False):
                self.last_fetch_magnets = fetch_magnets
                self.last_best_only = best_only
                return {
                    "magnets": ["magnet:?xt=urn:btih:roe556"],
                    "javdb_id": "1",
                    "number": number,
                    "title": "t",
                    "release_date": "2026-09-22",
                    "content_type": "jav_censored",
                    "content_type_label": "有码",
                    "has_cnsub": False,
                    "cnsub_magnet_count": 0,
                    "score": 4.34,
                    "reviews_count": 1329,
                    "watched_count": 130,
                    "query_status": "ok",
                    "magnet_status": "available",
                    "magnet_total": 3,
                    "magnet_filtered": 1,
                    "best_magnet": "magnet:?xt=urn:btih:roe556",
                }

        client = FakeJavDB()
        self.assertTrue(maybe_javdb_magnet_fallback(item, client))
        self.assertTrue(client.last_fetch_magnets)
        self.assertTrue(client.last_best_only)
        self.assertEqual(item["selected_magnet"], "magnet:?xt=urn:btih:roe556")
        self.assertEqual(item["av_number"], "ROE-556")
        self.assertEqual(item["javdb_query"]["number"], "ROE-556")

    def test_maybe_javdb_magnet_fallback_skips_when_gate_failed(self):
        item = {
            "title": "[有码] ROE-556",
            "skip_reason": "javdb_score_low_3.00",
            "magnets": [],
        }

        class FakeJavDB:
            def lookup(self, *args, **kwargs):
                raise AssertionError("lookup should not run when gate failed")

        self.assertFalse(maybe_javdb_magnet_fallback(item, FakeJavDB()))

    def test_javdb_non_cnsub_when_post_has_no_magnets(self):
        item = {
            "title": "[有码] ABC-123",
            "av_number": "ABC-123",
            "magnets": [],
        }

        class FakeJavDB:
            def lookup(self, number, *, fetch_magnets=False, cnsub=False, best_only=False):
                if cnsub:
                    return {"magnets": [], "query_status": "ok", "number": number}
                return {
                    "magnets": ["magnet:?xt=urn:btih:javdbplain"],
                    "javdb_id": "1",
                    "number": number,
                    "title": "t",
                    "release_date": "2026-01-01",
                    "content_type": "jav_censored",
                    "content_type_label": "有码",
                    "has_cnsub": False,
                    "cnsub_magnet_count": 0,
                    "score": 4.5,
                    "reviews_count": 100,
                    "query_status": "ok",
                }

        selection = select_magnet(item, javdb_client=FakeJavDB())
        self.assertEqual(selection["source"], "javdb_fallback")

    def test_build_number_downloads_prefers_cnsub_for_same_number(self):
        item = {
            "title": "[合集] batch",
            "magnets": [
                "magnet:?xt=urn:btih:plain&dn=ABC-123%20plain",
                "magnet:?xt=urn:btih:cnsub&dn=ABC-123-UC%20cnsub",
            ],
        }
        paired = build_number_downloads(item)
        self.assertEqual(len(paired), 1)
        self.assertEqual(paired[0]["av_number"], "ABC-123")
        self.assertTrue(magnet_has_cnsub(paired[0]["magnet"]))

    def test_apply_selection_upgrades_batch_entry_to_javdb_cnsub(self):
        item = {
            "title": "[合集] batch",
            "magnets": [
                "magnet:?xt=urn:btih:plain&dn=ABC-123%20plain",
                "magnet:?xt=urn:btih:bbb&dn=DEF-456%20plain",
            ],
        }

        class FakeJavDB:
            def lookup(self, number, *, fetch_magnets=False, cnsub=False, best_only=False):
                if cnsub and number == "ABC-123":
                    return {
                        "magnets": ["magnet:?xt=urn:btih:javdbcnsub"],
                        "javdb_id": "1",
                        "number": number,
                        "title": "t",
                        "release_date": "2026-01-01",
                        "content_type": "jav_censored",
                        "content_type_label": "有码",
                        "has_cnsub": True,
                        "cnsub_magnet_count": 1,
                        "score": 4.5,
                        "reviews_count": 100,
                        "query_status": "ok",
                    }
                return {"magnets": [], "query_status": "ok", "number": number}

        self.assertTrue(apply_selection(item, javdb_client=FakeJavDB()))
        by_num = {row["av_number"]: row for row in item["number_downloads"]}
        self.assertEqual(by_num["ABC-123"]["source"], "javdb_cnsub")
        self.assertEqual(by_num["ABC-123"]["magnet"], "magnet:?xt=urn:btih:javdbcnsub")
        self.assertEqual(by_num["DEF-456"]["source"], "forum_magnet_dn")


class ExtractAllNumbersTests(unittest.TestCase):
    def test_find_multiple_numbers(self):
        text = "合集 MIDA-790 + MFYD-182 和 PPPE-440"
        self.assertEqual(
            extract_all_av_numbers(text),
            ["MIDA-790", "MFYD-182", "PPPE-440"],
        )


class BuildNumberDownloadsTests(unittest.TestCase):
    def test_pairs_magnets_by_dn_number(self):
        item = {
            "title": "[合集资源] 【BT种子】20260914 黑客合集",
            "magnets": [
                "magnet:?xt=urn:btih:AAA&dn=MIDA-790%20title1",
                "magnet:?xt=urn:btih:BBB&dn=MFYD-182%20title2",
            ],
        }
        paired = build_number_downloads(item)
        self.assertEqual(len(paired), 2)
        self.assertEqual({p["av_number"] for p in paired}, {"MIDA-790", "MFYD-182"})

    def test_apply_selection_sets_number_downloads(self):
        item = {
            "title": "[合集资源] 【BT种子】合集",
            "magnets": [
                "magnet:?xt=urn:btih:AAA&dn=MIDA-790%20title1",
                "magnet:?xt=urn:btih:BBB&dn=MFYD-182%20title2",
            ],
        }
        self.assertTrue(apply_selection(item))
        self.assertEqual(len(item["number_downloads"]), 2)
        downloads = iter_item_downloads(item)
        self.assertEqual(len(downloads), 2)
        self.assertEqual(
            {d["av_number"] for d in downloads},
            {"MIDA-790", "MFYD-182"},
        )

    def test_number_from_magnet_reads_dn(self):
        mag = "magnet:?xt=urn:btih:abc&dn=EBWH-352%20test"
        self.assertEqual(number_from_magnet(mag), "EBWH-352")


if __name__ == "__main__":
    unittest.main()
