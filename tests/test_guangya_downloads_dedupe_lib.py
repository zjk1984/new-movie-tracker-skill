# -*- coding: utf-8 -*-
import unittest

from guangya_downloads_dedupe_lib import guangya_row_for_dedupe
from pikpak_downloads_dedupe_lib import (
    DEDUPE_FOLDER_TAG,
    cross_folder_dup_groups,
    group_tagged_files_by_av_number,
    pick_cross_folder_keeper_and_trash,
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

    def test_cross_folder_keeps_downloads(self) -> None:
        rows = [
            guangya_row_for_dedupe({"id": "a", "name": "ssis-001-C.mp4", "size": 100}, "downloads"),
            guangya_row_for_dedupe({"id": "b", "name": "ssis-001-UC.mp4", "size": 200}, "JAV"),
        ]
        groups, _ = group_tagged_files_by_av_number(rows, pseudo_as_jav=True)
        cross = cross_folder_dup_groups(groups, keeper_folder="downloads")
        self.assertIn("SSIS-001", cross)
        keeper, trash = pick_cross_folder_keeper_and_trash(cross["SSIS-001"], keeper_folder="downloads")
        self.assertEqual(keeper["id"], "a")
        self.assertEqual(trash[0]["id"], "b")
        self.assertEqual(trash[0][DEDUPE_FOLDER_TAG], "JAV")


if __name__ == "__main__":
    unittest.main()
