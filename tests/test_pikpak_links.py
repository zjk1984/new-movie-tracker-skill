# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from magnet_select import apply_selection, build_number_downloads  # noqa: E402
from pikpak_download import iter_item_downloads  # noqa: E402
from pikpak_links import (  # noqa: E402
    collect_alternatives_from_text,
    parse_collection_body_entries,
)


LAOHANGJIA_BODY = """
【影片名稱】：IPX-518 絲襪美腿女獄警
【中文片名】：IPX-518 絲襪美腿女獄警撩起短裙要我舔穴(字幕破解FHD)
【影片格式】：FHD1080P/MP4
【驗證全碼】：e5cb04dc5038b6edc01e12a685644d5de157a159
-----------------------------------------------------------------------------------------------------------------
【影片名稱】：IPX-647 突撃！単体女優
【中文片名】：IPX-647 女優紬明里調查風俗店體驗高潮報導(字幕破解FHD)
【影片格式】：FHD1080P/MP4
【驗證全碼】：be19ef79731b183f47767a13ca8a88bf07d6c46b
-----------------------------------------------------------------------------------------------------------------
【影片名稱】：IPX-569 形勢逆転
【中文片名】：IPX-569 酒店叫雞來的竟是黑絲美腿女上司(字幕破解FHD)
【驗證全碼】：110e5f142e9aa738db149275c84650eb4cbfe30e
"""


class ParseCollectionBodyTests(unittest.TestCase):
    def test_parse_laohangjia_blocks(self):
        entries = parse_collection_body_entries(LAOHANGJIA_BODY)
        self.assertEqual(len(entries), 3)
        self.assertEqual(
            {e["av_number"] for e in entries},
            {"IPX-518", "IPX-647", "IPX-569"},
        )
        self.assertTrue(all(e["uri"].startswith("magnet:?xt=urn:btih:") for e in entries))
        self.assertIn("絲襪美腿", entries[0]["chinese_title"])

    def test_collect_alternatives_includes_verify_codes(self):
        alts = collect_alternatives_from_text(LAOHANGJIA_BODY)
        self.assertEqual(len(alts["magnets"]), 3)
        self.assertEqual(len(alts["hash_entries"]), 3)
        numbers = {
            e.get("av_number")
            for e in alts["hash_entries"]
            if e.get("av_number")
        }
        self.assertEqual(numbers, {"IPX-518", "IPX-647", "IPX-569"})


class LaohangjiaBatchDownloadTests(unittest.TestCase):
    def test_build_number_downloads_pairs_verify_codes(self):
        item = {
            "title": "[亚洲无码] 【BT种子】09/20 老行家❤5部精選字幕FHD解密版❤",
            **collect_alternatives_from_text(LAOHANGJIA_BODY),
        }
        paired = build_number_downloads(item)
        self.assertEqual(len(paired), 3)
        self.assertEqual(
            {p["av_number"] for p in paired},
            {"IPX-518", "IPX-647", "IPX-569"},
        )

    def test_apply_selection_and_iter_downloads(self):
        item = {
            "title": "[亚洲无码] 【BT种子】09/20 老行家❤5部精選字幕FHD解密版❤",
            **collect_alternatives_from_text(LAOHANGJIA_BODY),
        }
        self.assertTrue(apply_selection(item))
        downloads = iter_item_downloads(item)
        self.assertEqual(len(downloads), 3)
        self.assertEqual(
            {d["av_number"] for d in downloads},
            {"IPX-518", "IPX-647", "IPX-569"},
        )


if __name__ == "__main__":
    unittest.main()
