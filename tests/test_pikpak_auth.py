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

    def test_inspect_jwt_token(self):
        import base64
        import json
        import time
        from pikpak_auth import inspect_jwt_token

        # Expired token
        header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').decode().rstrip("=")
        past_exp = int(time.time()) - 3600
        payload_expired = base64.urlsafe_b64encode(
            json.dumps({"sub": "user123", "exp": past_exp}).encode()
        ).decode().rstrip("=")
        fake_token_expired = f"{header}.{payload_expired}.sig"

        info_expired = inspect_jwt_token(fake_token_expired)
        self.assertTrue(info_expired["valid_jwt"])
        self.assertEqual(info_expired["sub"], "user123")
        self.assertTrue(info_expired["is_expired"])
        self.assertEqual(info_expired["status"], "expired")
        self.assertIn("过期", info_expired["message"])

        # Active token
        future_exp = int(time.time()) + 7200
        payload_active = base64.urlsafe_b64encode(
            json.dumps({"sub": "user456", "exp": future_exp}).encode()
        ).decode().rstrip("=")
        fake_token_active = f"{header}.{payload_active}.sig"

        info_active = inspect_jwt_token(fake_token_active)
        self.assertTrue(info_active["valid_jwt"])
        self.assertEqual(info_active["sub"], "user456")
        self.assertFalse(info_active["is_expired"])
        self.assertEqual(info_active["status"], "active")


if __name__ == "__main__":
    unittest.main()
