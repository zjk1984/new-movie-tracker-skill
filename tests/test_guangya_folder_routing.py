# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from guangya_folder import (  # noqa: E402
    DEFAULT_GUANGYA_FOLDER,
    guangya_folder_for_download_item,
    resolve_guangya_domestic_folder,
    resolve_guangya_folder,
    resolve_guangya_jav_folder,
)


class GuangyaFolderRoutingTests(unittest.TestCase):
    def test_defaults_my_pack(self) -> None:
        self.assertEqual(DEFAULT_GUANGYA_FOLDER, "My Pack")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_guangya_jav_folder(), "My Pack")
            self.assertEqual(resolve_guangya_domestic_folder(), "My Pack")
            self.assertEqual(resolve_guangya_folder(), "My Pack")

    def test_env_overrides(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "GUANGYAPAN_FOLDER_JAV": "Japan",
                "GUANGYAPAN_FOLDER_DOMESTIC": "CN",
                "GUANGYAPAN_FOLDER": "Fallback",
            },
            clear=True,
        ):
            self.assertEqual(resolve_guangya_jav_folder(), "Japan")
            self.assertEqual(resolve_guangya_domestic_folder(), "CN")
            self.assertEqual(resolve_guangya_folder(), "Fallback")

    def test_folder_for_download_item_by_region(self) -> None:
        self.assertEqual(
            guangya_folder_for_download_item({"region": "jav_censored"}, fallback="X"),
            "My Pack",
        )
        self.assertEqual(
            guangya_folder_for_download_item({"region": "uncensored"}, fallback="X"),
            "My Pack",
        )
        self.assertEqual(
            guangya_folder_for_download_item({"region": "domestic_leak"}, fallback="X"),
            "My Pack",
        )
        self.assertEqual(
            guangya_folder_for_download_item({"content_region": "jav_censored"}, fallback="Legacy"),
            "My Pack",
        )
        self.assertEqual(
            guangya_folder_for_download_item({}, fallback="Legacy"),
            "Legacy",
        )


if __name__ == "__main__":
    unittest.main()
