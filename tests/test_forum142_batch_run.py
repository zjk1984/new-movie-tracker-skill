# -*- coding: utf-8
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from forum142_batch_run import (  # noqa: E402
    DEFAULT_FORUM_URL,
    PAGES_PER_RUN,
    build_state_after_run,
    forum142_report_path,
    load_fresh_batch_result,
    load_fresh_download_report,
    resolve_next_start_page,
    save_state,
    state_path,
    write_forum142_daily_report,
)


class Forum142BatchRunTests(unittest.TestCase):
    def test_resolve_next_start_page_uses_saved_cursor(self):
        state = {"next_start_page": 210}
        self.assertEqual(resolve_next_start_page(state, initial_page=200), 210)

    def test_resolve_next_start_page_defaults_to_initial(self):
        self.assertEqual(resolve_next_start_page({}, initial_page=200), 200)

    def test_resolve_next_start_page_set_page_override(self):
        state = {"next_start_page": 210}
        self.assertEqual(
            resolve_next_start_page(state, initial_page=200, set_page=200),
            200,
        )

    def test_pages_per_run_default(self):
        self.assertEqual(PAGES_PER_RUN, 10)

    def test_default_forum_url_uses_sehuatang_net_fid142(self):
        self.assertEqual(
            DEFAULT_FORUM_URL,
            "https://www.sehuatang.net/forum-142-1.html",
        )
        self.assertNotIn("sehuatang.org", DEFAULT_FORUM_URL)

    def test_build_state_after_run_advances_cursor(self):
        out = build_state_after_run(
            forum_url=DEFAULT_FORUM_URL,
            initial_page=200,
            start_page=200,
            max_pages=PAGES_PER_RUN,
            previous={"runs_completed": 2},
        )
        self.assertEqual(out["last_start_page"], 200)
        self.assertEqual(out["last_end_page"], 209)
        self.assertEqual(out["next_start_page"], 210)
        self.assertEqual(out["pages_per_run"], 10)
        self.assertEqual(out["runs_completed"], 3)

    def test_save_and_load_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = state_path(Path(tmp))
            save_state(path, {"next_start_page": 210})
            self.assertEqual(path.read_text(encoding="utf-8").strip().startswith("{"), True)

    def test_forum142_report_path_uses_date(self):
        when = datetime(2026, 9, 26, 14, 0, 0)
        with tempfile.TemporaryDirectory() as tmp:
            path = forum142_report_path(reports_dir=Path(tmp), when=when)
            self.assertEqual(path.name, "forum-142_2026-09-26.md")

    def test_write_forum142_daily_report_minimal(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports_dir = Path(tmp) / "reports"
            batch_state = {"next_start_page": 210, "runs_completed": 1}
            path = write_forum142_daily_report(
                Path(tmp),
                start_page=200,
                end_page=209,
                batch_state=batch_state,
                reports_dir=reports_dir,
            )
            self.assertTrue(path.exists())
            text = path.read_text(encoding="utf-8")
            self.assertIn("Forum-142 批量扫描记录", text)
            self.assertIn("200~209", text)
            self.assertIn("210", text)

    def test_load_fresh_batch_result_rejects_stale_scan_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            result_path = Path(tmp) / "last_result.json"
            result_path.write_text(
                '{"scan_time":"2026-09-26T10:00:00","matched":[{"title":"old"}],"total_posts":300}',
                encoding="utf-8",
            )
            fresh = load_fresh_batch_result(
                result_path,
                not_before=datetime(2026, 9, 26, 15, 0, 0),
            )
            self.assertIsNone(fresh)

    def test_write_forum142_daily_report_ignores_stale_last_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            reports_dir = out / "reports"
            (out / "last_result.json").write_text(
                '{"scan_time":"2026-09-26T10:00:00","matched":[{"title":"old","href":"thread-1-1-1.html","forum":"x","actors":[],"matched_names":[],"keywords":[],"date":"2026-09-26","date_raw":"2026-09-26","content_region":"jp"}],"total_posts":300,"pages_scanned":10,"batch_mode":true}',
                encoding="utf-8",
            )
            (out / "download_report.json").write_text(
                '{"generated_at":"2026-09-26T10:05:00","ok":45,"failed_count":0,"total":45,"succeeded":[{"name":"old"}],"failed":[]}',
                encoding="utf-8",
            )
            path = write_forum142_daily_report(
                out,
                start_page=200,
                end_page=209,
                batch_state={"next_start_page": 210, "runs_completed": 1},
                reports_dir=reports_dir,
                batch_started_at=datetime(2026, 9, 26, 15, 0, 0),
            )
            text = path.read_text(encoding="utf-8")
            self.assertIn("无扫描结果文件 last_result.json", text)
            self.assertNotIn("300", text)
            self.assertNotIn("PikPak 成功", text)

    def test_write_forum142_daily_report_empty_current_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            reports_dir = out / "reports"
            batch_started = datetime(2026, 9, 26, 15, 0, 0)
            (out / "last_result.json").write_text(
                '{"scan_time":"2026-09-26T15:30:00","matched":[],"total_posts":0,"pages_scanned":10,"batch_mode":true}',
                encoding="utf-8",
            )
            (out / "download_report.json").write_text(
                '{"generated_at":"2026-09-26T10:05:00","ok":45,"failed_count":0,"total":45,"succeeded":[{"name":"old"}],"failed":[]}',
                encoding="utf-8",
            )
            path = write_forum142_daily_report(
                out,
                start_page=200,
                end_page=209,
                batch_state={"next_start_page": 210, "runs_completed": 1},
                reports_dir=reports_dir,
                batch_started_at=batch_started,
            )
            text = path.read_text(encoding="utf-8")
            self.assertIn("匹配帖 | 0", text)
            self.assertIn("PikPak 成功 | 0", text)
            self.assertNotIn("45", text)

    def test_load_fresh_download_report_empty_when_no_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "download_report.json"
            report_path.write_text(
                '{"generated_at":"2026-09-26T15:30:00","ok":45,"failed_count":0,"total":45,"succeeded":[],"failed":[]}',
                encoding="utf-8",
            )
            empty = load_fresh_download_report(
                report_path,
                not_before=datetime(2026, 9, 26, 15, 0, 0),
                matched_total=0,
            )
            self.assertEqual(empty["ok"], 0)
            self.assertEqual(empty["total"], 0)

    @patch.dict("os.environ", {"FEISHU_RECEIVE_ID": "oc_test"}, clear=False)
    @patch("forum142_batch_run.maybe_feishu_forum142_summary")
    @patch("forum142_batch_run.write_forum142_daily_report")
    @patch("forum142_batch_run.subprocess.call", return_value=0)
    @patch("forum142_batch_run.load_state", return_value={})
    def test_run_batch_defers_feishu_summary_and_notifies_with_forum142_report(
        self, _load, mock_call, mock_report, mock_feishu
    ):
        from argparse import Namespace

        from forum142_batch_run import run_batch

        report_path = Path("/tmp/reports/forum-142_2026-09-26.md")
        mock_report.return_value = report_path
        with tempfile.TemporaryDirectory() as tmp:
            args = Namespace(
                status=False,
                reset=False,
                output_dir=tmp,
                forum_url=DEFAULT_FORUM_URL,
                initial_page=200,
                max_pages=PAGES_PER_RUN,
                set_page=None,
                headless=True,
                scan_only=False,
                feishu=False,
                no_feishu=False,
                fetch_workers=5,
            )
            self.assertEqual(run_batch(args), 0)
        cmd = mock_call.call_args[0][0]
        self.assertIn("--defer-feishu-summary", cmd)
        self.assertIn("--run-label", cmd)
        self.assertEqual(cmd[cmd.index("--run-label") + 1], "forum-142")
        self.assertIn("--feishu", cmd)
        mock_feishu.assert_called_once()
        self.assertEqual(mock_feishu.call_args.args[1], report_path)
        self.assertTrue(mock_feishu.call_args.kwargs["enabled"])

    @patch("forum142_batch_run.maybe_feishu_forum142_summary")
    @patch("forum142_batch_run.write_forum142_daily_report")
    @patch("forum142_batch_run.subprocess.call", return_value=0)
    @patch("forum142_batch_run.load_state", return_value={})
    def test_run_batch_passes_batch_mode_and_fetch_workers(
        self, _load, mock_call, mock_report, _feishu
    ):
        from argparse import Namespace

        from forum142_batch_run import run_batch

        with tempfile.TemporaryDirectory() as tmp:
            args = Namespace(
                status=False,
                reset=False,
                output_dir=tmp,
                forum_url=DEFAULT_FORUM_URL,
                initial_page=200,
                max_pages=PAGES_PER_RUN,
                set_page=None,
                headless=True,
                scan_only=False,
                feishu=False,
                no_feishu=True,
                fetch_workers=5,
            )
            self.assertEqual(run_batch(args), 0)
        cmd = mock_call.call_args[0][0]
        self.assertIn("--batch-mode", cmd)
        self.assertIn("--fetch-workers", cmd)
        idx = cmd.index("--fetch-workers")
        self.assertEqual(cmd[idx + 1], "5")
        mock_report.assert_called_once()


if __name__ == "__main__":
    unittest.main()
