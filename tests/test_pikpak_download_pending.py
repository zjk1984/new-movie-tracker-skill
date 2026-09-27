# -*- coding: utf-8
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from pikpak_download import (  # noqa: E402
    extract_pending_submit_uris,
    save_download_report,
    submit_from_result,
)


class ExtractPendingSubmitUrisTests(unittest.TestCase):
    def test_from_pending_submit_on_auth_skip(self):
        report = {
            "submit_skip_reason": "auth:no_token",
            "pending_submit": [
                {"uri": "magnet:?xt=urn:btih:aaa"},
                {"uri": "ed2k://file|bbb|/"},
            ],
            "failed": [],
        }
        self.assertEqual(
            extract_pending_submit_uris(report),
            ["magnet:?xt=urn:btih:aaa", "ed2k://file|bbb|/"],
        )

    def test_from_failed_quota_errors(self):
        report = {
            "submit_skip_reason": "",
            "pending_submit": [],
            "failed": [
                {"uri": "magnet:?xt=urn:btih:quota1", "error": "task_daily_create_limit"},
                {"uri": "magnet:?xt=urn:btih:other", "error": "task_url_resolve_error"},
            ],
        }
        self.assertEqual(
            extract_pending_submit_uris(report),
            ["magnet:?xt=urn:btih:quota1"],
        )

    def test_merges_pending_and_failed_without_duplicates(self):
        report = {
            "submit_skip_reason": "auth:invalid",
            "pending_submit": [{"uri": "magnet:?xt=urn:btih:same"}],
            "failed": [
                {"uri": "magnet:?xt=urn:btih:same", "error": "HTTP 401"},
                {"uri": "magnet:?xt=urn:btih:other", "error": "Storage space is not enough"},
            ],
        }
        self.assertEqual(
            extract_pending_submit_uris(report),
            ["magnet:?xt=urn:btih:same", "magnet:?xt=urn:btih:other"],
        )


class SubmitFromResultAuthSkipTests(unittest.TestCase):
    def test_no_token_writes_pending_report(self):
        pending_item = {
            "name": "TEST-001",
            "title": "test post",
            "type": "url",
            "url": "magnet:?xt=urn:btih:pending123",
            "uri": "magnet:?xt=urn:btih:pending123",
            "magnet": "magnet:?xt=urn:btih:pending123",
            "href": "thread-1.html",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            result_path = out / "last_result.json"
            result_path.write_text("{}", encoding="utf-8")
            with patch("pikpak_download.load_downloads_from_result", return_value=[pending_item]):
                with patch("pikpak_auth.resolve_token", return_value=""):
                    ok, total = submit_from_result(
                        result_path,
                        today_only=False,
                        region_filter=True,
                        new_only=False,
                        skip_scan_repeat=False,
                    )
            report_path = out / "download_report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(ok, 0)
            self.assertEqual(total, 1)
            self.assertEqual(report["submit_skip_reason"], "auth:no_token")
            self.assertEqual(len(report["pending_submit"]), 1)
            self.assertEqual(
                extract_pending_submit_uris(report),
                ["magnet:?xt=urn:btih:pending123"],
            )


class SaveDownloadReportTests(unittest.TestCase):
    def test_persists_pending_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "download_report.json"
            save_download_report(
                path,
                succeeded=[],
                failed=[],
                pending_submit=[{"uri": "magnet:?xt=urn:btih:x"}],
                submit_skip_reason="auth:no_token",
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["submit_skip_reason"], "auth:no_token")
            self.assertEqual(data["pending_submit"][0]["uri"], "magnet:?xt=urn:btih:x")


if __name__ == "__main__":
    unittest.main()
