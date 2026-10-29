# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from pikpak_downloads_jav_scrape_lib import group_videos_by_av  # noqa: E402


def _row(name: str, fid: str = "x") -> dict:
    return {
        "kind": "drive#file",
        "phase": "PHASE_TYPE_COMPLETE",
        "name": name,
        "id": fid,
    }


class GroupByAvTests(unittest.TestCase):
    def test_same_av_multiple_files_one_group(self):
        videos = [
            (_row("SSIS-001-UC.mp4", "a"), "downloads-id"),
            (_row("SSIS-001-C.mp4", "b"), "downloads-id"),
        ]
        groups = group_videos_by_av(videos, pseudo_as_jav=False)
        self.assertEqual(list(groups.keys()), ["SSIS-001"])
        self.assertEqual(len(groups["SSIS-001"]), 2)


if __name__ == "__main__":
    unittest.main()
