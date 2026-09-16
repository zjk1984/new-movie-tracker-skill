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
    _build_undownloaded_entries,
    _match_reason_label,
    _md_success_sections,
    _md_table_cell_link,
    _md_undownloaded_posts,
    _previous_report_line,
    _skip_reason_label,
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
        self.assertIn("#### HMN-900 · JavDB 通过 · 4.14 · magnet · 4.14 · 下载中", section)
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

    def test_stats_rows_include_submit_funnel_breakdown(self):
        rows = scan_funnel_stats_rows(
            {
                "matched_total": 130,
                "with_link": 70,
                "downloadable": 108,
                "without_link": 38,
                "skipped_jav_score": 21,
                "link_totals": {"magnet": 245, "ed2k": 16, "bt": 121},
                "posts_with": {"magnet": 87, "ed2k": 15, "bt": 13},
                "submit_funnel": {
                    "expanded_links": 75,
                    "multi_link_posts": 2,
                    "submit_candidates": 75,
                    "scan_dedup_skipped": 124,
                    "new_only_skipped": 15,
                    "submitted_ok": 60,
                    "submitted_fail": 0,
                },
            },
            {"ok": 60, "failed_count": 0, "total": 60},
        )
        labels = [row[0] for row in rows]
        self.assertIn("待提交链接（展开）", labels)
        self.assertIn("扫描去重后", labels)
        self.assertIn("new_only 跳过", labels)
        expand_row = next(r for r in rows if r[0] == "待提交链接（展开）")
        self.assertEqual(expand_row[1], "75")
        skip_row = next(r for r in rows if r[0] == "new_only 跳过")
        self.assertEqual(skip_row[1], "15")


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


class UndownloadedPostsTests(unittest.TestCase):
    def test_includes_no_link_downloadable_post_with_translated_title(self):
        matched = [
            {
                "href": "thread-no-link.html",
                "title": "[有码] ABC-123 最高にエロい隣人",
                "content_region": "jav_censored",
                "av_number": "ABC-123",
                "javdb_query": {
                    "query_status": "ok",
                    "score": 4.5,
                    "release_date": "2026-01-01",
                    "reviews_count": 1500,
                    "title": "最高にエロい隣人",
                },
            },
        ]
        download_report = {"succeeded": [], "failed": []}
        with patch("title_translate.translate_title_for_item", return_value="最色情的邻居"):
            section = _md_undownloaded_posts(matched, download_report)
        self.assertIn("### 日本片（1 帖）", section)
        self.assertIn("ABC-123 · 链接未抓取", section)
        self.assertIn("最色情的邻居", section)
        self.assertIn('href="https://www.sehuatang.org/thread-no-link.html"', section)
        self.assertIn("_（无链接）_", section)
        self.assertNotIn("<pre><code>magnet:", section)

    def test_skips_no_link_post_when_href_already_succeeded(self):
        matched = [
            {
                "href": "thread-done.html",
                "title": "[国产] 酒店偷拍",
                "content_region": "domestic_leak",
                "domestic_subtype": "酒店偷拍",
            },
        ]
        download_report = {
            "succeeded": [{"href": "thread-done.html", "uri": "magnet:?xt=urn:btih:abc"}],
            "failed": [],
        }
        jav_entries, domestic_entries = _build_undownloaded_entries(matched, download_report)
        self.assertEqual(jav_entries, [])
        self.assertEqual(domestic_entries, [])

    def test_jav_success_sorted_by_release_date_desc(self):
        matched = [
            {
                "href": "thread-old.html",
                "title": "[有码] AAA-111 old",
                "content_region": "jav_censored",
                "av_number": "AAA-111",
                "javdb_query": {
                    "query_status": "ok",
                    "score": 4.5,
                    "release_date": "2024-06-01",
                },
            },
            {
                "href": "thread-new.html",
                "title": "[有码] BBB-222 new",
                "content_region": "jav_censored",
                "av_number": "BBB-222",
                "release_date": "2026-03-15",
            },
        ]
        succeeded = [
            {
                "href": "thread-old.html",
                "name": "AAA-111",
                "uri": "magnet:?xt=urn:btih:aaa",
            },
            {
                "href": "thread-new.html",
                "name": "BBB-222",
                "uri": "magnet:?xt=urn:btih:bbb",
            },
        ]
        with patch("title_translate.translate_title_for_item", side_effect=lambda i: i.get("title", "")):
            section = _md_success_sections(succeeded, matched)
        self.assertLess(section.index("BBB-222"), section.index("AAA-111"))

    def test_jav_undownloaded_sorted_by_release_date_desc(self):
        matched = [
            {
                "href": "thread-old.html",
                "title": "[有码] AAA-111 old",
                "content_region": "jav_censored",
                "av_number": "AAA-111",
                "javdb_query": {
                    "query_status": "ok",
                    "score": 4.5,
                    "release_date": "2024-06-01",
                },
                "magnets": ["magnet:?xt=urn:btih:aaa"],
            },
            {
                "href": "thread-new.html",
                "title": "[有码] BBB-222 new",
                "content_region": "jav_censored",
                "av_number": "BBB-222",
                "release_date": "2026-03-15",
                "magnets": ["magnet:?xt=urn:btih:bbb"],
            },
            {
                "href": "thread-nodate.html",
                "title": "[有码] CCC-333 nodate",
                "content_region": "jav_censored",
                "av_number": "CCC-333",
                "javdb_query": {"query_status": "ok", "score": 4.5},
                "magnets": ["magnet:?xt=urn:btih:ccc"],
            },
        ]
        download_report = {"succeeded": [], "failed": []}
        jav_entries, _ = _build_undownloaded_entries(matched, download_report)
        self.assertEqual(
            [e["label"] for e in jav_entries],
            ["BBB-222", "AAA-111", "CCC-333"],
        )

    def test_domestic_uses_chinese_title_and_thread_link(self):
        matched = [
            {
                "href": "thread-domestic.html",
                "title": "[国产] 素人ハメ撮り",
                "content_region": "domestic_leak",
                "domestic_subtype": "素人",
                "magnets": ["magnet:?xt=urn:btih:pending"],
            },
        ]
        download_report = {"succeeded": [], "failed": []}
        with patch("title_translate.translate_title_for_item", return_value="素人拍摄"):
            section = _md_undownloaded_posts(matched, download_report)
        self.assertIn("### 国产（1 帖）", section)
        self.assertIn("素人拍摄", section)
        self.assertIn('href="https://www.sehuatang.org/thread-domestic.html"', section)
        self.assertIn("<pre><code>magnet:?xt=urn:btih:pending</code></pre>", section)

    def test_domestic_undownloaded_sorted_by_post_date_desc(self):
        matched = [
            {
                "href": "thread-old.html",
                "title": "[国产] old post",
                "content_region": "domestic_leak",
                "domestic_subtype": "酒店偷拍",
                "date": "2024-06-01",
                "magnets": ["magnet:?xt=urn:btih:old"],
            },
            {
                "href": "thread-new.html",
                "title": "[国产] new post",
                "content_region": "domestic_leak",
                "domestic_subtype": "素人",
                "date": "2026-03-15",
                "magnets": ["magnet:?xt=urn:btih:new"],
            },
            {
                "href": "thread-nodate.html",
                "title": "[国产] no date",
                "content_region": "domestic_leak",
                "domestic_subtype": "ed2k",
                "magnets": ["magnet:?xt=urn:btih:nodate"],
            },
        ]
        download_report = {"succeeded": [], "failed": []}
        _, domestic_entries = _build_undownloaded_entries(matched, download_report)
        self.assertEqual(
            [e["href"] for e in domestic_entries],
            ["thread-new.html", "thread-old.html", "thread-nodate.html"],
        )

    def test_domestic_success_sorted_by_post_date_desc(self):
        matched = [
            {
                "href": "thread-old.html",
                "title": "[国产] old post",
                "content_region": "domestic_leak",
                "domestic_subtype": "酒店偷拍",
                "date": "2024-06-01",
            },
            {
                "href": "thread-new.html",
                "title": "[国产] new post",
                "content_region": "domestic_leak",
                "domestic_subtype": "素人",
                "date": "2026-03-15",
            },
            {
                "href": "thread-nodate.html",
                "title": "[国产] no date",
                "content_region": "domestic_leak",
                "domestic_subtype": "ed2k",
            },
        ]
        succeeded = [
            {"href": "thread-old.html", "name": "old", "uri": "magnet:?xt=urn:btih:old"},
            {"href": "thread-new.html", "name": "new", "uri": "magnet:?xt=urn:btih:new"},
            {"href": "thread-nodate.html", "name": "nodate", "uri": "magnet:?xt=urn:btih:nodate"},
        ]
        section = _md_success_sections(succeeded, matched)
        self.assertLess(section.index("new post"), section.index("old post"))
        self.assertLess(section.index("old post"), section.index("no date"))


class FilterReasonLabelTests(unittest.TestCase):
    def test_skip_reason_javdb_tag_excluded(self):
        item = {"skip_reason": "javdb_tag_excluded_淫语"}
        self.assertEqual(_skip_reason_label(item), "JavDB 标签排除: 淫语")

    def test_skip_reason_javdb_reviews_low(self):
        item = {"skip_reason": "javdb_reviews_low_50"}
        self.assertEqual(_skip_reason_label(item), "JavDB 评论数不足 (50)")

    def test_skip_reason_javdb_score_low(self):
        item = {"skip_reason": "javdb_score_low_3.50"}
        self.assertEqual(_skip_reason_label(item), "JavDB 评分 3.50 < 4")

    def test_skip_reason_no_link_fallback(self):
        item = {"content_region": "jav_censored"}
        self.assertEqual(_skip_reason_label(item), "未成功下载")

    def test_match_reason_jav_shows_score(self):
        matched = {
            "thread-1.html": {
                "href": "thread-1.html",
                "content_region": "jav_censored",
                "javdb_query": {"query_status": "ok", "score": 4.25},
            },
        }
        item = {"href": "thread-1.html", "name": "HMN-900"}
        reason = _match_reason_label(item, matched, is_jav=True)
        self.assertEqual(reason, "JavDB 通过 · 4.25")

    def test_match_reason_domestic_shows_subtype(self):
        matched = {
            "thread-2.html": {
                "href": "thread-2.html",
                "content_region": "domestic_leak",
                "domestic_subtype": "泄密",
            },
        }
        item = {"href": "thread-2.html", "name": "leak-post"}
        reason = _match_reason_label(item, matched, is_jav=False)
        self.assertEqual(reason, "匹配: 泄密")

    def test_undownloaded_jav_shows_skip_reason_after_number(self):
        matched = [
            {
                "href": "thread-low.html",
                "title": "[有码] LOW-111 test",
                "content_region": "jav_censored",
                "av_number": "LOW-111",
                "skip_reason": "javdb_tag_excluded_淫语",
                "magnets": ["magnet:?xt=urn:btih:low"],
            },
        ]
        download_report = {"succeeded": [], "failed": []}
        with patch("title_translate.translate_title_for_item", return_value="测试"):
            section = _md_undownloaded_posts(matched, download_report)
        self.assertIn("LOW-111 · JavDB 标签排除: 淫语", section)

    def test_success_jav_shows_match_reason_after_number(self):
        matched = [
            {
                "href": "thread-1.html",
                "title": "[有码] HMN-900 テスト",
                "content_region": "jav_censored",
                "javdb_query": {
                    "query_status": "ok",
                    "score": 4.14,
                    "number": "HMN-900",
                },
            },
        ]
        succeeded = [
            {
                "href": "thread-1.html",
                "name": "HMN-900",
                "uri": "magnet:?xt=urn:btih:abc",
                "phase": "PHASE_TYPE_RUNNING",
            },
        ]
        with patch("title_translate.translate_title_for_item", return_value="测试标题"):
            section = _md_success_sections(succeeded, matched)
        self.assertIn("#### HMN-900 · JavDB 通过 · 4.14 · magnet · 4.14 · 下载中", section)

    def test_success_domestic_shows_match_reason(self):
        matched = [
            {
                "href": "thread-dom.html",
                "title": "[国产] 泄密视频",
                "content_region": "domestic_leak",
                "domestic_subtype": "泄密",
            },
        ]
        succeeded = [
            {
                "href": "thread-dom.html",
                "name": "泄密",
                "uri": "ed2k://file|abc|/",
            },
        ]
        section = _md_success_sections(succeeded, matched)
        self.assertIn("#### [泄密] 泄密 · 匹配: 泄密 · ed2k · 已提交", section)


def _mida783_batch_thread() -> dict:
    """thread-3765040-style BT batch: 5 magnets, 5 distinct AV numbers."""
    return {
        "href": "thread-3765040-1-1.html",
        "title": "[合集资源] 【BT种子】20260915 ★黑客最新發布5部1080P★【AI破解版】",
        "content_region": "jav_censored",
        "av_number": "MIDA-783",
        "javdb_query": {
            "query_status": "ok",
            "number": "MIDA-783",
            "score": 4.2,
            "title": "MIDA-783 thread title",
        },
        "magnets": [
            "magnet:?xt=urn:btih:AAA&dn=MIDA-783%20最高にエロい",
            "magnet:?xt=urn:btih:BBB&dn=MFYD-186%20貞淑な地味妻",
            "magnet:?xt=urn:btih:CCC&dn=PRED-899%20美人上司",
            "magnet:?xt=urn:btih:DDD&dn=HMN-903%20昔好きだった",
            "magnet:?xt=urn:btih:EEE&dn=MIKR-122%20小柄な",
        ],
    }


class BatchSplitByNumberTests(unittest.TestCase):
    def test_undownloaded_batch_post_splits_into_five_entries(self):
        matched = [_mida783_batch_thread()]
        download_report = {"succeeded": [], "failed": []}
        with patch("title_translate.translate_title_for_item", side_effect=lambda i: i.get("name", "")):
            with patch("javdb_client.is_submit_eligible", return_value=True):
                jav_entries, domestic_entries = _build_undownloaded_entries(
                    matched,
                    download_report,
                )
        self.assertEqual(domestic_entries, [])
        self.assertEqual(len(jav_entries), 5)
        self.assertEqual(
            {e["label"] for e in jav_entries},
            {"MIDA-783", "MFYD-186", "PRED-899", "HMN-903", "MIKR-122"},
        )
        for entry in jav_entries:
            self.assertEqual(len(entry["links"]), 1)

    def test_undownloaded_single_magnet_post_unchanged(self):
        matched = [
            {
                "href": "thread-single.html",
                "title": "[有码] ABC-123 single",
                "content_region": "jav_censored",
                "av_number": "ABC-123",
                "magnets": ["magnet:?xt=urn:btih:single&dn=ABC-123%20test"],
            },
        ]
        download_report = {"succeeded": [], "failed": []}
        with patch("title_translate.translate_title_for_item", return_value="测试"):
            with patch("javdb_client.is_submit_eligible", return_value=True):
                jav_entries, _ = _build_undownloaded_entries(matched, download_report)
        self.assertEqual(len(jav_entries), 1)
        self.assertEqual(jav_entries[0]["label"], "ABC-123")
        self.assertEqual(len(jav_entries[0]["links"]), 1)

    def test_md_undownloaded_batch_shows_five_headers(self):
        matched = [_mida783_batch_thread()]
        download_report = {"succeeded": [], "failed": []}
        with patch("title_translate.translate_title_for_item", side_effect=lambda i: i.get("name", "")):
            with patch("javdb_client.is_submit_eligible", return_value=True):
                section = _md_undownloaded_posts(matched, download_report)
        self.assertIn("### 日本片（5 帖）", section)
        for num in ("MIDA-783", "MFYD-186", "PRED-899", "HMN-903", "MIKR-122"):
            self.assertIn(f"#### {num} ·", section)
        self.assertNotIn("# 2 [magnet]", section)

    def test_batch_split_queries_javdb_for_each_number(self):
        matched = [_mida783_batch_thread()]
        download_report = {"succeeded": [], "failed": []}

        def fake_attach(item, _client):
            number = (item.get("av_number") or "").upper()
            scores = {
                "MIDA-783": 4.2,
                "MFYD-186": 4.1,
                "PRED-899": 4.34,
                "HMN-903": 4.5,
                "MIKR-122": 3.9,
            }
            score = scores.get(number)
            item["javdb_query"] = {
                "query_status": "ok",
                "number": number,
                "score": score,
                "release_date": "2026-09-15",
                "reviews_count": 1200,
            }
            if score is not None and score < 4:
                item["skip_reason"] = f"javdb_score_low_{score:.2f}"

        with patch("title_translate.translate_title_for_item", side_effect=lambda i: i.get("name", "")):
            with patch("javdb_client.attach_javdb_query", side_effect=fake_attach):
                jav_entries, _ = _build_undownloaded_entries(matched, download_report)

        by_label = {entry["label"]: entry for entry in jav_entries}
        self.assertNotIn("JavDB 无评分", by_label["PRED-899"]["reason"])
        self.assertNotIn("JavDB 未查询", by_label["PRED-899"]["reason"])
        self.assertIn("JavDB 评分 3.90 < 4", by_label["MIKR-122"]["reason"])

    def test_success_batch_items_use_per_magnet_labels(self):
        thread = _mida783_batch_thread()
        matched = [thread]
        succeeded = [
            {
                "href": thread["href"],
                "name": "MFYD-186 貞淑な地味妻",
                "uri": thread["magnets"][1],
                "phase": "PHASE_TYPE_COMPLETE",
            },
            {
                "href": thread["href"],
                "name": "MIDA-783 最高にエロい",
                "uri": thread["magnets"][0],
                "phase": "PHASE_TYPE_COMPLETE",
            },
        ]
        with patch("title_translate.translate_title_for_item", side_effect=lambda i: i.get("name", "")):
            section = _md_success_sections(succeeded, matched)
        self.assertIn("#### MIDA-783 ·", section)
        self.assertIn("#### MFYD-186 ·", section)
        self.assertIn("magnet:?xt=urn:btih:AAA", section)
        self.assertIn("magnet:?xt=urn:btih:BBB", section)


class MdTableCellLinkTests(unittest.TestCase):
    def test_plain_text_without_url(self):
        self.assertEqual(_md_table_cell_link("hello", ""), "hello")

    def test_link_escapes_special_chars(self):
        cell = _md_table_cell_link('a & b', "https://example.com/?q=1")
        self.assertIn("&amp;", cell)
        self.assertIn("https://example.com/?q=1", cell)


if __name__ == "__main__":
    unittest.main()
