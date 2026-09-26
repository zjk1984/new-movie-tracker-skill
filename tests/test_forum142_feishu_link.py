# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from feishu_notify import notify_cards  # noqa: E402
from run_report import github_blob_url, report_github_branch  # noqa: E402


class Forum142FeishuLinkTests(unittest.TestCase):
    @patch("feishu_notify.send_interactive_card", return_value={"code": 0})
    @patch("feishu_notify._push_report_and_url")
    @patch("feishu_notify._prepare_notify_payload")
    def test_notify_cards_links_existing_forum142_report(
        self,
        mock_prepare,
        mock_push,
        _send,
    ):
        mock_prepare.return_value = (
            {
                "scan_time": "2026-09-26T13:00:00+08:00",
                "forums": {"forum-142 有码": 2},
                "matched_total": 2,
                "downloadable": 2,
                "with_link": 2,
                "without_link": 0,
                "link_totals": {"magnet": 2, "ed2k": 0, "bt": 0},
                "posts_with": {"magnet": 2, "ed2k": 0, "bt": 0},
                "matched": [],
            },
            {"ok": 1, "failed_count": 0, "total": 1, "succeeded": [], "failed": []},
            Path("/tmp/data"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            result_path = data_dir / "last_result.json"
            result_path.write_text(
                json.dumps({"matched": [], "scan_time": "2026-09-26T13:00:00+08:00"}),
                encoding="utf-8",
            )
            reports_dir = Path(tmp) / "reports"
            reports_dir.mkdir()
            when = datetime(2026, 9, 26, 13, 0, 0)
            existing = reports_dir / f"forum-142_{when.strftime('%Y-%m-%d')}.md"
            existing.write_text("# Forum-142 batch report\n", encoding="utf-8")

            expected_url = github_blob_url(
                f"reports/{existing.name}",
                branch=report_github_branch(),
            )
            mock_push.return_value = expected_url

            _, report_path, report_url = notify_cards(
                [result_path],
                existing_report_path=existing,
            )

            self.assertEqual(report_path, existing.resolve())
            self.assertEqual(report_url, expected_url)
            mock_push.assert_called_once()
            pushed_path = mock_push.call_args.args[0]
            self.assertEqual(pushed_path.name, "forum-142_2026-09-26.md")
            self.assertFalse(pushed_path.name.startswith("custom_"))
            self.assertFalse(pushed_path.name.startswith("daily_"))


if __name__ == "__main__":
    unittest.main()
