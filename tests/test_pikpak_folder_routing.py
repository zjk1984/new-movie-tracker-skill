# -*- coding: utf-8
from __future__ import annotations

import os
import sys
import unittest
import base64
import json
import time
from unittest.mock import patch

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from pikpak_auth import (  # noqa: E402
    folder_for_download_item,
    resolve_domestic_folder,
    resolve_jav_folder,
)
from pikpak_download import submit_downloads  # noqa: E402


class FolderResolverTests(unittest.TestCase):
    def test_default_jav_and_domestic_folders(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PIKPAK_FOLDER_JAV", None)
            os.environ.pop("PIKPAK_FOLDER_DOMESTIC", None)
            self.assertEqual(resolve_jav_folder(), "JAV")
            self.assertEqual(resolve_domestic_folder(), "My Pack")

    def test_env_overrides(self):
        with patch.dict(
            os.environ,
            {"PIKPAK_FOLDER_JAV": "Japan", "PIKPAK_FOLDER_DOMESTIC": "CN"},
            clear=False,
        ):
            self.assertEqual(resolve_jav_folder(), "Japan")
            self.assertEqual(resolve_domestic_folder(), "CN")

    def test_folder_for_download_item_by_region(self):
        self.assertEqual(
            folder_for_download_item({"region": "jav_censored"}, fallback="My Pack"),
            "JAV",
        )
        self.assertEqual(
            folder_for_download_item({"region": "uncensored"}, fallback="My Pack"),
            "JAV",
        )
        self.assertEqual(
            folder_for_download_item({"region": "domestic_leak"}, fallback="My Pack"),
            "My Pack",
        )
        self.assertEqual(
            folder_for_download_item({"content_region": "jav_censored"}, fallback="Legacy"),
            "JAV",
        )
        self.assertEqual(
            folder_for_download_item({}, fallback="Legacy"),
            "Legacy",
        )


class SubmitDownloadsFolderRoutingTests(unittest.TestCase):
    def test_routes_items_to_jav_and_domestic_folders(self):
        items = [
            {
                "name": "SSIS-001",
                "title": "jav",
                "type": "url",
                "url": "magnet:?xt=urn:btih:jav1",
                "uri": "magnet:?xt=urn:btih:jav1",
                "region": "jav_censored",
            },
            {
                "name": "国产流出",
                "title": "domestic",
                "type": "url",
                "url": "magnet:?xt=urn:btih:cn1",
                "uri": "magnet:?xt=urn:btih:cn1",
                "region": "domestic_leak",
            },
        ]
        header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').decode().rstrip("=")
        future_exp = int(time.time()) + 7200
        payload_b64 = base64.urlsafe_b64encode(
            json.dumps({"sub": "user1", "exp": future_exp}).encode()
        ).decode().rstrip("=")
        token = f"{header}.{payload_b64}.sig"
        folder_ids = {"JAV": "pid-jav", "My Pack": "pid-cn"}

        def fake_find_folder(session, access_token, device_id, user_id, folder_name):
            return folder_ids.get(folder_name)

        with patch("pikpak_auth.resolve_token", return_value=token), patch(
            "pikpak_download.find_folder_id",
            side_effect=fake_find_folder,
        ), patch(
            "pikpak_download.submit_one_download",
            return_value={"task": {"id": "t1", "phase": "PHASE_TYPE_PENDING"}},
        ) as submit_mock:
            ok, total, succeeded, failed, pending, reason = submit_downloads(
                items,
                folder="My Pack",
                access_token=token,
            )

        self.assertEqual(ok, 2)
        self.assertEqual(total, 2)
        self.assertEqual(failed, [])
        self.assertEqual(pending, [])
        self.assertEqual(reason, "")
        parent_ids = [call.kwargs.get("parent_id") for call in submit_mock.call_args_list]
        self.assertEqual(parent_ids, ["pid-jav", "pid-cn"])


if __name__ == "__main__":
    unittest.main()
