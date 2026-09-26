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
    PAGES_PER_RUN,
    build_state_after_run,
    forum142_report_path,
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

    def test_build_state_after_run_advances_cursor(self):
        out = build_state_after_run(
            forum_url="https://www.sehuatang.org/forum-142-1.html",
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
        when = datetime(2026, 9, 26, 13, 0, 0)
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

    @patch("forum142_batch_run.write_forum142_daily_report")
    @patch("forum142_batch_run.subprocess.call", return_value=0)
    @patch("forum142_batch_run.load_state", return_value={})
    def test_run_batch_passes_batch_mode_and_fetch_workers(
        self, _load, mock_call, mock_report
    ):
        from argparse import Namespace

        from forum142_batch_run import run_batch

        with tempfile.TemporaryDirectory() as tmp:
            args = Namespace(
                status=False,
                reset=False,
                output_dir=tmp,
                forum_url="https://www.sehuatang.org/forum-142-1.html",
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
        self.assertIn("--batch-mode", cmd)
        self.assertIn("--fetch-workers", cmd)
        idx = cmd.index("--fetch-workers")
        self.assertEqual(cmd[idx + 1], "5")
        mock_report.assert_called_once()


if __name__ == "__main__":
    unittest.main()
