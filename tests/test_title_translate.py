# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from submit_gate import build_submit_probe  # noqa: E402
from title_translate import source_text_for_item, translate_title_for_item  # noqa: E402


class TitleTranslatePerNumberTests(unittest.TestCase):
    def test_compilation_post_uses_per_magnet_title_not_thread_javdb(self):
        thread = {
            "href": "thread-3765040-1-1.html",
            "title": "[合集资源] 【BT种子】20260915 ★黑客最新發布5部1080P★【AI破解版】",
            "content_region": "jav_censored",
            "av_number": "HMN-903",
            "javdb_query": {
                "query_status": "ok",
                "number": "HMN-903",
                "title": "昔好きだった同級生が借金まみれになっていたので、当時のあの子にそっくりな娘を俺専用身代わり肉便器メイド1週間24発で雇った 鈴の家りん",
            },
        }
        matched_by_href = {thread["href"]: thread}

        hmn = build_submit_probe(
            {
                "href": thread["href"],
                "name": "HMN-903 昔好きだった同級生が借金まみれになっていたので、当時のあの子にそっくりな娘を俺専用身代わり肉便器メイド1週間24発で雇った 鈴の家りん",
                "uri": "magnet:?xt=urn:btih:2652D0B596DDFD4E31B90D5598C77744E54C026C&dn=HMN-903%20%E6%98%94%E5%A5%BD%E3%81%8D%E3%81%A0%E3%81%A3%E3%81%9F",
                "av_number": "HMN-903",
            },
            matched_by_href,
        )
        mfyd = build_submit_probe(
            {
                "href": thread["href"],
                "name": "MFYD-186 貞淑な地味妻がドM覚醒！いつでもどこでもドS男にバチボコ犯●れるSM調教デート",
                "uri": "magnet:?xt=urn:btih:C350B99D712400BEF9931F781188DF035B9EECCA&dn=MFYD-186%20%E8%B2%9E%E6%B7%91",
                "av_number": "MFYD-186",
            },
            matched_by_href,
        )

        hmn_src = source_text_for_item(hmn)
        mfyd_src = source_text_for_item(mfyd)
        self.assertIn("同級生", hmn_src)
        self.assertIn("地味妻", mfyd_src)
        self.assertNotEqual(hmn_src, mfyd_src)

    def test_translate_uses_distinct_source_per_number(self):
        item_a = {
            "content_region": "jav_censored",
            "av_number": "HMN-903",
            "name": "HMN-903 昔好きだった同級生",
            "javdb_query": {"number": "HMN-903", "title": "昔好きだった同級生"},
        }
        item_b = {
            "content_region": "jav_censored",
            "av_number": "MFYD-186",
            "name": "MFYD-186 貞淑な地味妻がドM覚醒",
            "javdb_query": {"number": "HMN-903", "title": "昔好きだった同級生"},
        }
        with patch("title_translate.translate_ja_to_zh", side_effect=lambda t: f"ZH:{t}"):
            self.assertEqual(
                translate_title_for_item(item_a),
                "ZH:昔好きだった同級生",
            )
            self.assertEqual(
                translate_title_for_item(item_b),
                "ZH:貞淑な地味妻がドM覚醒",
            )


if __name__ == "__main__":
    unittest.main()
