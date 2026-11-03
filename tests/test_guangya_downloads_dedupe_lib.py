# -*- coding: utf-8 -*-
import unittest

from guangya_downloads_dedupe_lib import (
    cross_folder_dup_groups_tiered,
    guangya_row_for_dedupe,
    pick_tiered_cross_folder_keeper_and_trash,
)
from pikpak_downloads_dedupe_lib import (
    DEDUPE_FOLDER_TAG,
    group_tagged_files_by_av_number,
    pick_keeper_and_trash,
)

CROSS_PRIORITY = ["downloads", "Save", "JAV"]


class GuangyaDedupeLibTests(unittest.TestCase):
    def test_pick_keeper_uc_over_c(self) -> None:
        rows = [
            guangya_row_for_dedupe({"id": "1", "name": "abf-161-C.mp4", "size": 100}, "downloads"),
            guangya_row_for_dedupe({"id": "2", "name": "ABF-161-UC.mp4", "size": 50}, "downloads"),
        ]
        keeper, trash = pick_keeper_and_trash(rows)
        self.assertEqual(keeper["id"], "2")
        self.assertEqual(len(trash), 1)

    def test_cross_folder_keeps_downloads_over_jav(self) -> None:
        rows = [
            guangya_row_for_dedupe({"id": "a", "name": "ssis-001-C.mp4", "size": 100}, "downloads"),
            guangya_row_for_dedupe({"id": "b", "name": "ssis-001-UC.mp4", "size": 200}, "JAV"),
        ]
        groups, _ = group_tagged_files_by_av_number(rows, pseudo_as_jav=True)
        cross = cross_folder_dup_groups_tiered(groups)
        self.assertIn("SSIS-001", cross)
        kf, keeper, trash = pick_tiered_cross_folder_keeper_and_trash(
            cross["SSIS-001"],
            folder_priority=CROSS_PRIORITY,
        )
        self.assertEqual(kf, "downloads")
        self.assertEqual(keeper["id"], "a")
        self.assertEqual(trash[0]["id"], "b")
        self.assertEqual(trash[0][DEDUPE_FOLDER_TAG], "JAV")

    def test_cross_folder_save_jav_keeps_save(self) -> None:
        rows = [
            guangya_row_for_dedupe({"id": "s", "name": "abc-100-UC.mp4", "size": 200}, "Save"),
            guangya_row_for_dedupe({"id": "j", "name": "abc-100-C.mp4", "size": 300}, "JAV"),
        ]
        groups, _ = group_tagged_files_by_av_number(rows, pseudo_as_jav=True)
        cross = cross_folder_dup_groups_tiered(groups)
        self.assertIn("ABC-100", cross)
        kf, keeper, trash = pick_tiered_cross_folder_keeper_and_trash(
            cross["ABC-100"],
            folder_priority=CROSS_PRIORITY,
        )
        self.assertEqual(kf, "Save")
        self.assertEqual(keeper["id"], "s")
        self.assertEqual(trash[0]["id"], "j")

    def test_cross_folder_all_three_keeps_downloads(self) -> None:
        rows = [
            guangya_row_for_dedupe({"id": "d", "name": "mid-001-UC.mp4", "size": 100}, "downloads"),
            guangya_row_for_dedupe({"id": "s", "name": "mid-001-C.mp4", "size": 50}, "Save"),
            guangya_row_for_dedupe({"id": "j", "name": "mid-001.mp4", "size": 200}, "JAV"),
        ]
        groups, _ = group_tagged_files_by_av_number(rows, pseudo_as_jav=True)
        cross = cross_folder_dup_groups_tiered(groups)
        self.assertIn("MID-001", cross)
        kf, keeper, trash = pick_tiered_cross_folder_keeper_and_trash(
            cross["MID-001"],
            folder_priority=CROSS_PRIORITY,
        )
        self.assertEqual(kf, "downloads")
        self.assertEqual(keeper["id"], "d")
        self.assertEqual({r["id"] for r in trash}, {"s", "j"})


if __name__ == "__main__":
    unittest.main()
