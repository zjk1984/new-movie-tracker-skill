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
    scan_funnel_stats_rows,
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
        self.assertIn("#### HMN-900 · magnet · 4.14 · 下载中", section)
        self.assertIn("**标题**:", section)
        self.assertIn("测试标题", section)
        self.assertIn("thread-1.html", section)
        self.assertIn("<pre><code>magnet:?xt=urn:btih:abc</code></pre>", section)
        self.assertNotIn("| 名称 | 类型 | 评分 |", section)


class ScanFunnelStatsTests(unittest.TestCase):
    def test_stats_rows_follow_funnel_order(self):
        rows = scan_funnel_stats_rows(
            {
                "matched_total": 311,
                "link_totals": {"magnet": 574, "ed2k": 62, "bt": 241},
                "posts_with": {"magnet": 172, "ed2k": 57, "bt": 40},
                "downloadable": 206,
                "with_link": 129,
                "without_link": 77,
                "skipped_jav_score": 24,
            },
            {"ok": 101, "failed_count": 0, "total": 101},
        )
        labels = [row[0] for row in rows]
        self.assertEqual(labels[0], "匹配帖")
        self.assertEqual(labels[1], "采集链接合计")
        self.assertEqual(rows[1][1], "877")
        self.assertEqual(labels[5], "可下载（过滤保留）")
        self.assertIn("PikPak 合计", labels[-1])


class ReportArchiveTests(unittest.TestCase):
    def test_archive_moves_root_reports_to_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports_dir = Path(tmp)
            old = reports_dir / "daily_2026-09-13_120000.md"
            old.write_text("# old", encoding="utf-8")
            previous, archived = archive_reports_to_backup(reports_dir, "daily")
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
            previous, archived = archive_reports_to_backup(reports_dir, "daily")
            self.assertEqual(previous, backed)
            self.assertEqual(archived, [])

    def test_daily_and_custom_timelines_are_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports_dir = Path(tmp)
            daily_old = reports_dir / "daily_2026-09-13_120000.md"
            custom_old = reports_dir / "custom_2026-09-13_130000.md"
            daily_old.write_text("# daily", encoding="utf-8")
            custom_old.write_text("# custom", encoding="utf-8")

            previous, archived = archive_reports_to_backup(reports_dir, "daily")
            self.assertFalse(daily_old.exists())
            self.assertTrue(custom_old.exists())
            self.assertEqual(len(archived), 1)
            self.assertEqual(previous.name, "daily_2026-09-13_120000.md")

            scan_stats = {
                "scan_time": "2026-09-13T14:00:00",
                "forums": {},
                "link_totals": {},
                "posts_with": {},
                "matched": [],
            }
            download_report = {
                "ok": 0,
                "failed_count": 0,
                "total": 0,
                "succeeded": [],
                "failed": [],
            }
            daily_result = write_run_report(
                scan_stats,
                download_report,
                reports_dir=reports_dir,
                run_label="daily",
            )
            daily_body = daily_result.path.read_text(encoding="utf-8")
            self.assertIn("daily_2026-09-13_120000.md", daily_body)
            self.assertNotIn("custom_2026-09-13_130000.md", daily_body)

            custom_result = write_run_report(
                scan_stats,
                download_report,
                reports_dir=reports_dir,
                run_label="custom",
            )
            custom_body = custom_result.path.read_text(encoding="utf-8")
            self.assertIn("custom_2026-09-13_130000.md", custom_body)
            self.assertNotIn("daily_2026-09-13_120000.md", custom_body)
            self.assertTrue(daily_result.path.exists())
            self.assertTrue(custom_result.path.exists())

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
    def test_github_link_uses_report_branch_not_current_branch(self):
        reports_dir = ROOT / "reports"
        previous = reports_dir / "backup" / "_test_previous_report_line.md"
        previous.parent.mkdir(parents=True, exist_ok=True)
        previous.write_text("x", encoding="utf-8")
        try:
            with patch("run_report._github_repo_slug", return_value="owner/repo"):
                with patch("run_report.report_github_branch", return_value="main"):
                    with patch("run_report.current_git_branch", return_value="cursor/feature-branch"):
                        line = _previous_report_line(previous, reports_dir=reports_dir)
            self.assertIn("/blob/main/", line)
            self.assertNotIn("/blob/cursor/", line)
        finally:
            previous.unlink(missing_ok=True)

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
