# -*- coding: utf-8
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from guangya_save_drive_inventory import (  # noqa: E402
    av_from_filename,
    is_video_file,
)


class VideoInventoryTests(unittest.TestCase):
    def test_nfo_not_video(self) -> None:
        self.assertFalse(is_video_file({"name": "SSIS-001.nfo", "size": 1000}))

    def test_mp4_is_video(self) -> None:
        self.assertTrue(is_video_file({"name": "489155.com@ADN-148-C.mp4", "size": 1}))

    def test_poster_not_video(self) -> None:
        self.assertFalse(is_video_file({"name": "SSIS-001-poster.jpg", "size": 1}))

    def test_loose_av_from_compact(self) -> None:
        self.assertEqual(av_from_filename("ADN148.mp4"), "ADN-148")

    def test_hyphen_av_in_name(self) -> None:
        self.assertEqual(av_from_filename("@bo99.tv_JUL-981.mp4"), "JUL-981")


if __name__ == "__main__":
    unittest.main()
