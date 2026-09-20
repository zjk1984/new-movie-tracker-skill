# -*- coding: utf-8
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from magnet_select import apply_selection  # noqa: E402
from pikpak_links import collect_alternatives_from_text  # noqa: E402
from scan import _thread_defers_javdb_gate, apply_item_filters  # noqa: E402


LAOHANGJIA_BODY = """
【中文片名】：IPX-518 絲襪美腿女獄警撩起短裙(字幕破解FHD)
【驗證全碼】：e5cb04dc5038b6edc01e12a685644d5de157a159
【中文片名】：IPX-647 女優紬明里調查風俗店(字幕破解FHD)
【驗證全碼】：be19ef79731b183f47767a13ca8a88bf07d6c46b
"""


class ThreadJavdbGateDeferTests(unittest.TestCase):
    def test_laohangjia_defers_thread_level_gate(self):
        item = {
            "title": "[亚洲无码] 【BT种子】09/20 老行家❤5部精選字幕FHD解密版❤",
            **collect_alternatives_from_text(LAOHANGJIA_BODY),
        }
        apply_selection(item)
        self.assertTrue(_thread_defers_javdb_gate(item))
        self.assertIsNone(item.get("av_number"))

    @patch("javdb_client.ensure_javdb_score_gate")
    @patch("javdb_client.attach_javdb_query")
    def test_apply_item_filters_skips_gate_for_collection(
        self,
        mock_attach,
        mock_gate,
    ):
        item = {
            "title": "[亚洲无码] 【BT种子】09/20 老行家❤5部精選字幕FHD解密版❤",
            **collect_alternatives_from_text(LAOHANGJIA_BODY),
        }
        apply_selection(item)
        args = SimpleNamespace(region_filter=True, javdb_query=True)
        apply_item_filters(item, MagicMock(), args)
        mock_gate.assert_not_called()
        mock_attach.assert_not_called()
        self.assertTrue(item.get("number_downloads"))


if __name__ == "__main__":
    unittest.main()
