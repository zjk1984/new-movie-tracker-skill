# -*- coding: utf-8
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from pikpak_auth import (  # noqa: E402
    classify_submit_error,
    format_submit_skip_reason,
    is_auth_or_quota_error,
)


class ClassifySubmitErrorTests(unittest.TestCase):
    def test_auth_no_token(self):
        self.assertEqual(
            classify_submit_error("no PikPak token: run login"),
            "auth",
        )

    def test_auth_http_401(self):
        self.assertEqual(classify_submit_error("list files failed: HTTP 401"), "auth")

    def test_quota_daily_limit(self):
        self.assertEqual(
            classify_submit_error("task_daily_create_limit exceeded"),
            "quota",
        )

    def test_quota_space(self):
        self.assertEqual(
            classify_submit_error("Storage space is not enough"),
            "quota",
        )

    def test_other_error_returns_none(self):
        self.assertIsNone(classify_submit_error("task_url_resolve_error"))

    def test_is_auth_or_quota_error(self):
        self.assertTrue(is_auth_or_quota_error("HTTP 403 forbidden"))
        self.assertFalse(is_auth_or_quota_error("feature code not in PikPak cache"))

    def test_format_submit_skip_reason(self):
        self.assertEqual(format_submit_skip_reason("auth", "no token"), "auth:no_token")


if __name__ == "__main__":
    unittest.main()
