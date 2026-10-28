# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from pikpak_downloads_dedupe_lib import (  # noqa: E402
    av_number_for_jav_dedupe,
    classify_filename_variant,
    cross_folder_dup_groups,
    dedupe_sort_key,
    domestic_dedupe_sort_key,
    domestic_group_key,
    group_files_by_av_number,
    group_files_domestic,
    group_tagged_files_by_av_number,
    normalize_domestic_filename,
    parse_folder_list,
    pick_cross_folder_keeper_and_trash,
    pick_keeper_and_trash,
    pick_keeper_and_trash_domestic,
    tag_row_folder,
)
from javdb_client import extract_av_number  # noqa: E402


def _file(name: str, size: int, file_id: str = "id", **extra: object) -> dict:
    row = {
        "kind": "drive#file",
        "phase": "PHASE_TYPE_COMPLETE",
        "name": name,
        "size": str(size),
        "id": file_id,
    }
    row.update(extra)
    return row


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


class NormalizeDomesticFilenameTests(unittest.TestCase):
    def test_strips_site_prefix_and_resolution(self):
        a = normalize_domestic_filename("489155.com@某酒店偷拍 1080p.mp4")
        b = normalize_domestic_filename("hhd800.com@某酒店偷拍 FHD x264.mp4")
        self.assertEqual(a, b)

    def test_bracket_and_copy_suffix(self):
        norm = normalize_domestic_filename("【首发】国产长标题测试(1).mkv")
        self.assertNotIn("【", norm)
        self.assertNotIn("(1)", norm)
        self.assertIn("国产长标题测试", norm)

    def test_extension_lowercase(self):
        self.assertTrue(normalize_domestic_filename("clip.MP4").endswith(".mp4"))


class DomesticGroupKeyTests(unittest.TestCase):
    def test_btih_wins_over_title(self):
        btih = "A" * 40
        row = _file(f"movie btih:{btih}.mp4", 100, "a")
        self.assertEqual(domestic_group_key(row), f"btih:{btih}")

    def test_hash_before_title(self):
        row = _file("long domestic title 1080p.mp4", 100, "a", hash="abc123")
        self.assertEqual(domestic_group_key(row), "hash:ABC123")

    def test_same_normalized_title_one_group(self):
        f1 = _file("489155.com@秘密花园 720p.mp4", 100, "a")
        f2 = _file("javkok.com@秘密花园 HD.mp4", 200, "b")
        self.assertEqual(domestic_group_key(f1), domestic_group_key(f2))

    def test_short_title_uses_file_id_no_merge(self):
        f1 = _file("酒店.mp4", 100, "id1")
        f2 = _file("酒店.mkv", 100, "id2")
        self.assertNotEqual(domestic_group_key(f1), domestic_group_key(f2))


class DomesticGroupingTests(unittest.TestCase):
    def test_group_by_normalized_title(self):
        files = [
            _file("489155.com@秘密花园 1080p.mp4", 100, "a"),
            _file("hhd800.com@秘密花园 720p.mp4", 500, "b"),
            _file("MIDV-671-UC.mp4", 1, "jav"),
        ]
        groups, candidates = group_files_domestic(files, pseudo_as_jav=False)
        title_keys = [k for k in groups if k.startswith("title:")]
        self.assertEqual(len(title_keys), 1)
        self.assertEqual(len(groups[title_keys[0]]), 2)
        self.assertEqual(candidates, 2)

    def test_domestic_keeper_size_then_name(self):
        files = [
            _file("489155.com@秘密花园 1080p.mp4", 100, "small"),
            _file("hhd800.com@秘密花园 720p.mp4", 500, "big"),
        ]
        keeper, trash = pick_keeper_and_trash_domestic(files)
        self.assertEqual(keeper["id"], "big")
        self.assertEqual(trash[0]["id"], "small")

    def test_pseudo_jav_routes_to_domestic_by_default(self):
        files = [
            _file("489155.com@XJX-12345 国产系列 1080p.mp4", 100, "a"),
            _file("hhd800.com@XJX-12345 国产系列 720p.mp4", 200, "b"),
        ]
        jav_groups, _ = group_files_by_av_number(files, pseudo_as_jav=False)
        self.assertEqual(jav_groups, {})
        dom_groups, _ = group_files_domestic(files, pseudo_as_jav=False)
        dup = [k for k, v in dom_groups.items() if len(v) >= 2]
        self.assertEqual(len(dup), 1)

    def test_pseudo_jav_as_jav_when_env_on(self):
        files = [
            _file("XJX-12345-A.mp4", 100, "a"),
            _file("XJX-12345-B.mp4", 200, "b"),
        ]
        jav_groups, _ = group_files_by_av_number(files, pseudo_as_jav=True)
        self.assertIn("XJX-12345", jav_groups)
        self.assertEqual(len(jav_groups["XJX-12345"]), 2)
        dom_groups, candidates = group_files_domestic(files, pseudo_as_jav=True)
        self.assertEqual(candidates, 0)
        self.assertEqual(dom_groups, {})


class PseudoJavRoutingTests(unittest.TestCase):
    def test_av_number_for_jav_default_skips_pseudo(self):
        name = "MDSY-999 标题.mp4"
        self.assertIsNone(av_number_for_jav_dedupe(name, pseudo_as_jav=False))
        self.assertEqual(av_number_for_jav_dedupe(name, pseudo_as_jav=True), "MDSY-999")


class CrossFolderDedupeTests(unittest.TestCase):
    def test_parse_folder_list(self):
        self.assertEqual(parse_folder_list(" downloads , JAV "), ["downloads", "JAV"])

    def test_cross_folder_dup_groups_requires_downloads(self):
        rows = [
            tag_row_folder(_file("MIDV-671-C.mp4", 100, "jav1"), "JAV"),
            tag_row_folder(_file("MIDV-671.mp4", 200, "jav2"), "JAV"),
        ]
        groups, _ = group_tagged_files_by_av_number(rows, pseudo_as_jav=False)
        self.assertEqual(cross_folder_dup_groups(groups), {})

    def test_cross_folder_trash_jav_keep_downloads(self):
        rows = [
            tag_row_folder(_file("ADN-549-C.mp4", 9_000_000_000, "jav"), "JAV"),
            tag_row_folder(_file("adn-549.mp4", 5_000_000_000, "dl"), "downloads"),
        ]
        groups, _ = group_tagged_files_by_av_number(rows, pseudo_as_jav=False)
        cross = cross_folder_dup_groups(groups)
        self.assertIn("ADN-549", cross)
        keeper, trash = pick_cross_folder_keeper_and_trash(cross["ADN-549"])
        self.assertEqual(keeper["id"], "dl")
        self.assertEqual(len(trash), 1)
        self.assertEqual(trash[0]["id"], "jav")

    def test_cross_folder_uc_in_downloads_over_jav_c(self):
        rows = [
            tag_row_folder(_file("MIDV-671-C.mp4", 9_000_000_000, "jav"), "JAV"),
            tag_row_folder(_file("MIDV-671-UC.mp4", 100, "dl"), "downloads"),
        ]
        groups, _ = group_tagged_files_by_av_number(rows, pseudo_as_jav=False)
        cross = cross_folder_dup_groups(groups)
        keeper, trash = pick_cross_folder_keeper_and_trash(cross["MIDV-671"])
        self.assertEqual(keeper["id"], "dl")
        self.assertEqual(trash[0]["id"], "jav")

    def test_cross_folder_extra_downloads_trashed(self):
        rows = [
            tag_row_folder(_file("ABC-123-C.mp4", 500, "jav"), "JAV"),
            tag_row_folder(_file("ABC-123.mp4", 100, "dl-plain"), "downloads"),
            tag_row_folder(_file("ABC-123-UC.mp4", 200, "dl-uc"), "downloads"),
        ]
        groups, _ = group_tagged_files_by_av_number(rows, pseudo_as_jav=False)
        cross = cross_folder_dup_groups(groups)
        keeper, trash = pick_cross_folder_keeper_and_trash(cross["ABC-123"])
        self.assertEqual(keeper["id"], "dl-uc")
        trash_ids = {r["id"] for r in trash}
        self.assertEqual(trash_ids, {"jav", "dl-plain"})


class DomesticSortKeyTests(unittest.TestCase):
    def test_domestic_sort_key(self):
        rows = sorted(
            [
                _file("a.mp4", 50, "s"),
                _file("b.mp4", 100, "b"),
            ],
            key=domestic_dedupe_sort_key,
        )
        self.assertEqual(rows[0]["id"], "b")


if __name__ == "__main__":
    unittest.main()
