# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from pikpak_downloads_dedupe_lib import (  # noqa: E402
    classify_filename_variant,
    dedupe_sort_key,
    pick_keeper_and_trash,
)
from javdb_client import extract_av_number  # noqa: E402


def _file(name: str, size: int, file_id: str = "id") -> dict:
    return {
        "kind": "drive#file",
        "phase": "PHASE_TYPE_COMPLETE",
        "name": name,
        "size": str(size),
        "id": file_id,
    }


class ClassifyVariantTests(unittest.TestCase):
    def test_uc_highest(self):
        self.assertEqual(classify_filename_variant("MIDV-671-UC.mp4"), 2)
        self.assertEqual(classify_filename_variant("MFYD-190-UC.mkv"), 2)

    def test_c_not_uc(self):
        self.assertEqual(classify_filename_variant("MIDV-671-C.mp4"), 1)
        self.assertEqual(classify_filename_variant("JUR-836-C.mp4"), 1)

    def test_neutral_u_and_plain(self):
        self.assertEqual(classify_filename_variant("MFYD-190-U.mp4"), 0)
        self.assertEqual(classify_filename_variant("JUR-836.mp4"), 0)


class PickKeeperTests(unittest.TestCase):
    def test_uc_over_u(self):
        files = [
            _file("MFYD-190-U.mp4", 5_000_000_000, "a"),
            _file("MFYD-190-UC.mp4", 1_000_000, "b"),
        ]
        keeper, trash = pick_keeper_and_trash(files)
        self.assertEqual(keeper["id"], "b")
        self.assertEqual(len(trash), 1)
        self.assertEqual(trash[0]["id"], "a")

    def test_uc_over_c(self):
        files = [
            _file("MIDV-671-C.mp4", 9_000_000_000, "c"),
            _file("MIDV-671-UC.mp4", 100, "uc"),
        ]
        keeper, trash = pick_keeper_and_trash(files)
        self.assertEqual(keeper["id"], "uc")

    def test_c_over_plain(self):
        files = [
            _file("JUR-836.mp4", 9_000_000_000, "plain"),
            _file("JUR-836-C.mp4", 100, "c"),
        ]
        keeper, trash = pick_keeper_and_trash(files)
        self.assertEqual(keeper["id"], "c")

    def test_larger_size_when_same_variant(self):
        files = [
            _file("ABC-123.mp4", 100, "small"),
            _file("ABC-123-1080p.mp4", 500, "big"),
        ]
        keeper, _ = pick_keeper_and_trash(files)
        self.assertEqual(keeper["id"], "big")

    def test_name_asc_tiebreak(self):
        files = [
            _file("XYZ-001-b.mp4", 100, "b"),
            _file("XYZ-001-a.mp4", 100, "a"),
        ]
        keeper, trash = pick_keeper_and_trash(files)
        self.assertEqual(keeper["id"], "a")
        self.assertEqual(trash[0]["id"], "b")


class ExtractAvNumberIntegrationTests(unittest.TestCase):
    def test_extract_on_sample_names(self):
        self.assertEqual(extract_av_number("MIDV-671-UC.mp4"), "MIDV-671")
        self.assertEqual(extract_av_number("MFYD-190-U.mp4"), "MFYD-190")


class SortKeyStabilityTests(unittest.TestCase):
    def test_sort_key_order(self):
        rows = [
            _file("T-1-UC.mp4", 1),
            _file("T-1-C.mp4", 999),
            _file("T-1.mp4", 999),
        ]
        ordered = sorted(rows, key=dedupe_sort_key)
        self.assertEqual(ordered[0]["name"], "T-1-UC.mp4")


if __name__ == "__main__":
    unittest.main()
