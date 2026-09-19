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
    number_from_magnet,
)
from pikpak_download import iter_item_downloads  # noqa: E402


class MagnetCnsubTests(unittest.TestCase):
    def test_magnet_has_cnsub_uc_suffix(self):
        mag = "magnet:?xt=urn:btih:abc&dn=ABC-123-UC%20title"
        self.assertTrue(magnet_has_cnsub(mag))


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
