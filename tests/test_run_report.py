# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from run_report import (  # noqa: E402
    _md_success_sections,
    _md_table_cell_link,
    _previous_report_line,
    _success_full_title,
    _success_name_cell,
    archive_reports_to_backup,
    write_run_report,
)


class SuccessNameCellTests(unittest.TestCase):
    def test_full_title_from_matched_post(self):
        matched = {
            "thread-1.html": {
                "href": "thread-1.html",
                "title": "[有码] MIDA-753 最高にエロい隣人",
            },
        }
        item = {
            "href": "thread-1.html",
            "name": "MIDA-753",
            "title": "[有码] MIDA-753 最高にエロい隣人",
            "uri": "magnet:?xt=urn:btih:abc",
        }
        self.assertEqual(
            _success_full_title(item, matched),
            "[有码] MIDA-753 最高にエロい隣人",
        )

    def test_jav_name_cell_uses_chinese_and_link(self):
        matched = {
            "thread-1.html": {
                "href": "thread-1.html",
                "title": "[有码] MIDA-753 最高にエロい隣人",
                "content_region": "jav_censored",
                "javdb_query": {
                    "query_status": "ok",
                    "score": 4.25,
                    "title": "最高にエロい隣人",
                },
            },
        }
        item = {
            "href": "thread-1.html",
            "name": "MIDA-753",
            "title": "[有码] MIDA-753 最高にエロい隣人",
            "uri": "magnet:?xt=urn:btih:abc",
        }
        with patch("title_translate.translate_title_for_item", return_value="最色情的邻居"):
            cell = _success_name_cell(item, matched, is_jav=True)
        self.assertIn("最色情的邻居", cell)
        self.assertIn('href="https://www.sehuatang.org/thread-1.html"', cell)

    def test_domestic_name_cell_uses_full_title_and_link(self):
        matched = {
            "thread-2.html": {
                "href": "thread-2.html",
                "title": "[国产] 酒店偷拍 小少妇",
                "content_region": "domestic_leak",
                "domestic_subtype": "酒店偷拍",
            },
        }
        item = {
            "href": "thread-2.html",
            "name": "6-17酒店偷拍",
            "title": "[国产] 酒店偷拍 小少妇",
            "uri": "magnet:?xt=urn:btih:def",
        }
        cell = _success_name_cell(item, matched, is_jav=False)
        self.assertIn("[国产] 酒店偷拍 小少妇", cell)
        self.assertIn('href="https://www.sehuatang.org/thread-2.html"', cell)

    def test_md_success_sections_renders_linked_names(self):
        matched = [
            {
                "href": "thread-1.html",
                "title": "[有码] HMN-900 テストタイトル",
                "content_region": "jav_censored",
                "javdb_query": {
                    "query_status": "ok",
                    "score": 4.14,
                    "number": "HMN-900",
                    "title": "テストタイトル",
                },
            },
        ]
        succeeded = [
            {
                "href": "thread-1.html",
                "name": "HMN-900",
                "title": "[有码] HMN-900 テストタイトル",
                "uri": "magnet:?xt=urn:btih:abc",
                "phase": "PHASE_TYPE_RUNNING",
            },
        ]
        with patch("title_translate.translate_title_for_item", return_value="测试标题"):
            section = _md_success_sections(succeeded, matched)
        self.assertIn("测试标题", section)
        self.assertIn("thread-1.html", section)
        self.assertNotRegex(section, r"\| HMN-900 \| magnet")


class ReportArchiveTests(unittest.TestCase):
    def test_archive_moves_root_reports_to_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports_dir = Path(tmp)
            old = reports_dir / "daily_2026-09-13_120000.md"
            old.write_text("# old", encoding="utf-8")
            previous, archived = archive_reports_to_backup(reports_dir)
            self.assertFalse(old.exists())
            self.assertEqual(len(archived), 1)
            self.assertEqual(archived[0].parent.name, "backup")
            self.assertEqual(previous, archived[0])

    def test_previous_report_from_backup_when_root_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports_dir = Path(tmp)
            backup = reports_dir / "backup"
            backup.mkdir()
            backed = backup / "daily_2026-09-13_120000.md"
            backed.write_text("# old", encoding="utf-8")
            previous, archived = archive_reports_to_backup(reports_dir)
            self.assertEqual(previous, backed)
            self.assertEqual(archived, [])

    def test_write_run_report_includes_previous_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports_dir = Path(tmp)
            old = reports_dir / "daily_2026-09-13_120000.md"
            old.write_text("# old", encoding="utf-8")
            scan_stats = {
                "scan_time": "2026-09-13T12:00:00",
                "forums": {},
                "link_totals": {},
                "posts_with": {},
                "matched": [],
            }
            download_report = {"ok": 0, "failed_count": 0, "total": 0, "succeeded": [], "failed": []}
            result = write_run_report(
                scan_stats,
                download_report,
                reports_dir=reports_dir,
                run_label="daily",
            )
            body = result.path.read_text(encoding="utf-8")
            self.assertIn("上一份报告", body)
            self.assertIn("daily_2026-09-13_120000.md", body)
            self.assertFalse(old.exists())
            self.assertTrue((reports_dir / "backup" / "daily_2026-09-13_120000.md").exists())


class PreviousReportLineTests(unittest.TestCase):
    def test_relative_link_when_no_github(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports_dir = Path(tmp)
            previous = reports_dir / "backup" / "daily_2026-09-13_120000.md"
            previous.parent.mkdir(parents=True)
            previous.write_text("x", encoding="utf-8")
            with patch("run_report.github_blob_url", return_value=None):
                line = _previous_report_line(previous, reports_dir=reports_dir)
            self.assertIn("[daily_2026-09-13_120000.md](backup/daily_2026-09-13_120000.md)", line)


class MdTableCellLinkTests(unittest.TestCase):
    def test_plain_text_without_url(self):
        self.assertEqual(_md_table_cell_link("hello", ""), "hello")

    def test_link_escapes_special_chars(self):
        cell = _md_table_cell_link('a & b', "https://example.com/?q=1")
        self.assertIn("&amp;", cell)
        self.assertIn("https://example.com/?q=1", cell)


if __name__ == "__main__":
    unittest.main()
