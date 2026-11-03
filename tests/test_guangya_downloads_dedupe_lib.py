# -*- coding: utf-8 -*-
import unittest

from guangya_downloads_dedupe_lib import (
    cross_folder_dup_groups,
    guangya_row_for_dedupe,
    pick_global_cross_folder_keeper_and_trash,
)
from pikpak_downloads_dedupe_lib import (
    DEDUPE_FOLDER_TAG,
    group_tagged_files_by_av_number,
    pick_keeper_and_trash,
)


class GuangyaDedupeLibTests(unittest.TestCase):
    def test_pick_keeper_uc_over_c(self) -> None:
        rows = [
            guangya_row_for_dedupe({"id": "1", "name": "abf-161-C.mp4", "size": 100}, "downloads"),
            guangya_row_for_dedupe({"id": "2", "name": "ABF-161-UC.mp4", "size": 50}, "downloads"),
        ]
        keeper, trash = pick_keeper_and_trash(rows)
        self.assertEqual(keeper["id"], "2")
        self.assertEqual(len(trash), 1)

    def test_cross_global_keeps_uc_in_save_over_c_in_downloads(self) -> None:
        rows = [
            guangya_row_for_dedupe({"id": "d", "name": "ssis-001-C.mp4", "size": 999}, "downloads"),
            guangya_row_for_dedupe({"id": "s", "name": "SSIS-001-UC.mp4", "size": 1}, "Save"),
        ]
        groups, _ = group_tagged_files_by_av_number(rows, pseudo_as_jav=True)
        cross = cross_folder_dup_groups(groups)
        kf, keeper, trash = pick_global_cross_folder_keeper_and_trash(cross["SSIS-001"])
        self.assertEqual(kf, "Save")
        self.assertEqual(keeper["id"], "s")
        self.assertEqual(len(trash), 1)
        self.assertEqual(trash[0]["id"], "d")

    def test_cross_global_keeps_uc_in_downloads_over_c_in_jav(self) -> None:
        rows = [
            guangya_row_for_dedupe({"id": "d", "name": "abc-200-UC.mp4", "size": 10}, "downloads"),
            guangya_row_for_dedupe({"id": "j", "name": "abc-200-C.mp4", "size": 900}, "JAV"),
        ]
        groups, _ = group_tagged_files_by_av_number(rows, pseudo_as_jav=True)
        cross = cross_folder_dup_groups(groups)
        kf, keeper, trash = pick_global_cross_folder_keeper_and_trash(cross["ABC-200"])
        self.assertEqual(kf, "downloads")
        self.assertEqual(keeper["id"], "d")
        self.assertEqual(trash[0][DEDUPE_FOLDER_TAG], "JAV")

    def test_cross_global_three_folders_picks_single_best(self) -> None:
        rows = [
            guangya_row_for_dedupe({"id": "d", "name": "mid-001.mp4", "size": 500}, "downloads"),
            guangya_row_for_dedupe({"id": "s", "name": "MID-001-UC.mp4", "size": 100}, "Save"),
            guangya_row_for_dedupe({"id": "j", "name": "mid-001-C.mp4", "size": 800}, "JAV"),
        ]
        groups, _ = group_tagged_files_by_av_number(rows, pseudo_as_jav=True)
        cross = cross_folder_dup_groups(groups)
        kf, keeper, trash = pick_global_cross_folder_keeper_and_trash(cross["MID-001"])
        self.assertEqual(kf, "Save")
        self.assertEqual(keeper["id"], "s")
        self.assertEqual({r["id"] for r in trash}, {"d", "j"})


if __name__ == "__main__":
    unittest.main()
