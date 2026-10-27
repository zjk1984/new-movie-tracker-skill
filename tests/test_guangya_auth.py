# -*- coding: utf-8
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from guangya_auth import (  # noqa: E402
    classify_submit_error,
    clear_credentials,
    format_submit_skip_reason,
    load_auth_store,
    resolve_access_token,
    resolve_client_id,
    resolve_refresh_token,
    save_credentials,
)


class GuangyaAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._auth_path = Path(self._tmpdir.name) / "guangya_auth.json"
        self._env_patch = mock.patch.dict(
            "os.environ",
            {
                "GUANGYA_AUTH_FILE": str(self._auth_path),
                "GUANGYA_ACCESS_TOKEN": "",
                "GUANGYA_REFRESH_TOKEN": "",
                "GUANGYA_CLIENT_ID": "",
            },
            clear=False,
        )
        self._env_patch.start()

    def tearDown(self) -> None:
        self._env_patch.stop()
        self._tmpdir.cleanup()

    def test_save_and_load_auth_store(self) -> None:
        save_credentials(
            client_id="test-client",
            access_token="access-abc",
            refresh_token="refresh-xyz",
            device_id="device-1",
        )
        store = load_auth_store()
        self.assertEqual(store["client_id"], "test-client")
        self.assertEqual(store["access_token"], "access-abc")
        self.assertEqual(store["refresh_token"], "refresh-xyz")
        self.assertEqual(store["device_id"], "device-1")
        self.assertIn("updated", store)
        mode = self._auth_path.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_resolve_token_precedence(self) -> None:
        save_credentials(access_token="saved-token", refresh_token="saved-refresh")
        self.assertEqual(resolve_access_token("explicit"), "explicit")
        with mock.patch.dict("os.environ", {"GUANGYA_ACCESS_TOKEN": "env-token"}):
            self.assertEqual(resolve_access_token(None), "env-token")
        with mock.patch.dict("os.environ", {"GUANGYA_ACCESS_TOKEN": ""}):
            self.assertEqual(resolve_access_token(None), "saved-token")

    def test_resolve_client_id(self) -> None:
        save_credentials(client_id="file-id", access_token="t")
        self.assertEqual(resolve_client_id("cli-id"), "cli-id")
        with mock.patch.dict("os.environ", {"GUANGYA_CLIENT_ID": "env-id"}):
            self.assertEqual(resolve_client_id(None), "env-id")

    def test_clear_credentials(self) -> None:
        save_credentials(access_token="x", refresh_token="y")
        self.assertTrue(self._auth_path.exists())
        self.assertTrue(clear_credentials())
        self.assertFalse(self._auth_path.exists())
        self.assertFalse(clear_credentials())

    def test_classify_submit_error(self) -> None:
        self.assertEqual(classify_submit_error("HTTP 401 unauthorized"), "auth")
        self.assertEqual(classify_submit_error("storage space is not enough"), "quota")
        self.assertIsNone(classify_submit_error("magnet parse error"))

    def test_format_submit_skip_reason(self) -> None:
        self.assertEqual(format_submit_skip_reason("auth", "no token"), "auth:no_token")

    def test_resolve_refresh_token(self) -> None:
        save_credentials(access_token="a", refresh_token="r1")
        self.assertEqual(resolve_refresh_token("r2"), "r2")


if __name__ == "__main__":
    unittest.main()
