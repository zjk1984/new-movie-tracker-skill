# -*- coding: utf-8
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from guangya_download import (  # noqa: E402
    GUANGYA_V1_UNSUPPORTED_ED2K,
    GUANGYA_V1_UNSUPPORTED_SHA,
    prepare_guangya_item,
)


class PrepareGuangyaItemTests(unittest.TestCase):
    def test_accepts_magnet(self) -> None:
        item = {"type": "url", "uri": "magnet:?xt=urn:btih:abc", "name": "X"}
        prepared, err = prepare_guangya_item(item)
        self.assertIsNone(err)
        assert prepared is not None
        self.assertTrue(prepared["uri"].startswith("magnet:"))

    def test_rejects_ed2k(self) -> None:
        item = {"type": "url", "uri": "ed2k://|file|a.mkv|123|hash|/", "name": "X"}
        _, err = prepare_guangya_item(item)
        self.assertEqual(err, GUANGYA_V1_UNSUPPORTED_ED2K)

    def test_rejects_sha(self) -> None:
        item = {"type": "sha", "hash": "abc", "name": "X"}
        _, err = prepare_guangya_item(item)
        self.assertEqual(err, GUANGYA_V1_UNSUPPORTED_SHA)


if __name__ == "__main__":
    unittest.main()
