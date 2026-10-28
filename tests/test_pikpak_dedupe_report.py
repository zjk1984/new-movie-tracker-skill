# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from pikpak_dedupe_report import (  # noqa: E402
    build_pikpak_dedupe_report_body,
    format_file_size,
    variant_rank_label,
)
from run_report import archive_reports_to_backup, write_pikpak_dedupe_report  # noqa: E402


class VariantLabelTests(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(variant_rank_label(2), "UC")
        self.assertEqual(variant_rank_label(1), "C")
        self.assertEqual(variant_rank_label(0), "普通")


class BuildBodyTests(unittest.TestCase):
    def test_dry_run_body_contains_groups(self):
        body = build_pikpak_dedupe_report_body(
            generated_at="2026-10-28 14:00:00",
            folder="downloads",
            parent_id="pid123",
            apply=False,
            stats={
                "total_files": 10,
                "av_groups": 8,
                "duplicate_groups": 1,
                "skipped_no_av": 2,
                "trash_candidates": 1,
                "trashed_ok": 0,
            },
            groups=[
                {
                    "av_number": "MIDV-671",
                    "keeper": {"name": "MIDV-671-UC.mp4", "size": 5_000_000_000, "variant_rank": 2},
                    "trash": [
                        {
                            "name": "MIDV-671-C.mp4",
                            "size": 4_000_000_000,
                            "variant_rank": 1,
                            "id": "file-c",
                        },
                    ],
                },
            ],
            previous_line="- **上一份报告**: [old.md](backup/old.md)\n",
        )
        self.assertIn("PikPak downloads 去重报告", body)
        self.assertIn("预览（dry-run", body)
        self.assertIn("MIDV-671", body)
        self.assertIn("MIDV-671-UC.mp4", body)
        self.assertIn("MIDV-671-C.mp4", body)
        self.assertIn("上一份报告", body)
        self.assertIn("将删除（预览）", body)

    def test_domestic_section_in_body(self):
        body = build_pikpak_dedupe_report_body(
            generated_at="2026-10-28 14:00:00",
            folder="downloads",
            parent_id=None,
            apply=False,
            stats={
                "total_files": 5,
                "av_groups": 1,
                "duplicate_groups": 0,
                "skipped_no_av": 4,
                "trash_candidates": 0,
                "domestic_candidates": 4,
                "domestic_duplicate_groups": 1,
                "domestic_trash_candidates": 1,
                "trashed_ok": 0,
            },
            groups=[],
            domestic_groups=[
                {
                    "group_key": "title:秘密花园.mp4",
                    "keeper": {"name": "hhd800.com@秘密花园 720p.mp4", "size": 500},
                    "trash": [
                        {
                            "name": "489155.com@秘密花园 1080p.mp4",
                            "size": 100,
                            "id": "dom-1",
                        },
                    ],
                },
            ],
        )
        self.assertIn("无番号 / 国产去重", body)
        self.assertIn("国产重复组", body)
        self.assertIn("秘密花园", body)
        self.assertIn("489155.com@秘密花园 1080p.mp4", body)

    def test_apply_body_shows_trash_status(self):
        body = build_pikpak_dedupe_report_body(
            generated_at="2026-10-28 14:00:00",
            folder="downloads",
            parent_id=None,
            apply=True,
            stats={
                "total_files": 3,
                "av_groups": 2,
                "duplicate_groups": 1,
                "skipped_no_av": 0,
                "trash_candidates": 1,
                "trashed_ok": 1,
            },
            groups=[
                {
                    "av_number": "ABC-123",
                    "keeper": {"name": "ABC-123-UC.mp4", "size": 100, "variant_rank": 2},
                    "trash": [
                        {
                            "name": "ABC-123.mp4",
                            "size": 50,
                            "variant_rank": 0,
                            "id": "x",
                            "trashed_ok": True,
                        },
                    ],
                },
            ],
        )
        self.assertIn("执行（已移入回收站）", body)
        self.assertIn("成功", body)


class WritePikpakDedupeReportTests(unittest.TestCase):
    def test_archives_previous_pikpak_dedupe_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports_dir = Path(tmp)
            old = reports_dir / "pikpak_dedupe_2026-09-13_120000.md"
            old.write_text("# old", encoding="utf-8")
            daily = reports_dir / "daily_2026-09-13_120000.md"
            daily.write_text("# daily", encoding="utf-8")

            result = write_pikpak_dedupe_report(
                folder="downloads",
                parent_id="parent-1",
                apply=False,
                stats={
                    "total_files": 0,
                    "av_groups": 0,
                    "duplicate_groups": 0,
                    "skipped_no_av": 0,
                    "trash_candidates": 0,
                    "domestic_candidates": 0,
                    "domestic_duplicate_groups": 0,
                    "domestic_trash_candidates": 0,
                    "trashed_ok": 0,
                },
                groups=[],
                reports_dir=reports_dir,
            )

            self.assertTrue(result.path.name.startswith("pikpak_dedupe_"))
            self.assertTrue(result.path.name.endswith(".md"))
            self.assertFalse(old.exists())
            self.assertTrue(daily.exists())
            body = result.path.read_text(encoding="utf-8")
            self.assertIn("pikpak_dedupe_2026-09-13_120000.md", body)
            self.assertIn("无重复番号组", body)
            self.assertTrue((reports_dir / "backup" / "pikpak_dedupe_2026-09-13_120000.md").exists())

    def test_archive_independent_from_daily(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports_dir = Path(tmp)
            old_dedupe = reports_dir / "pikpak_dedupe_2026-09-13_120000.md"
            old_dedupe.write_text("# dedupe", encoding="utf-8")
            previous, archived = archive_reports_to_backup(reports_dir, "pikpak_dedupe")
            self.assertEqual(len(archived), 1)
            self.assertEqual(previous.name, "pikpak_dedupe_2026-09-13_120000.md")

    def test_report_name_re_matches_pikpak_dedupe(self):
        from run_report import REPORT_NAME_RE

        self.assertIsNotNone(REPORT_NAME_RE.match("pikpak_dedupe_2026-10-28_153045.md"))


class FormatSizeTests(unittest.TestCase):
    def test_bytes(self):
        self.assertIn("1,024 B", format_file_size(1024))


if __name__ == "__main__":
    unittest.main()
