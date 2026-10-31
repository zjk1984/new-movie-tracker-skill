# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from guangya_cloud_daily import (  # noqa: E402
    cloud_apply_enabled,
    item_to_cloud_row,
    submit_from_result,
)


class GuangyaCloudDailyTests(unittest.TestCase):
    def test_item_to_cloud_row_magnet(self) -> None:
        row = item_to_cloud_row(
            {
                "type": "url",
                "uri": "magnet:?xt=urn:btih:abc",
                "name": "SSIS-001",
                "region": "jav_censored",
            },
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertTrue(row["uri"].startswith("magnet:"))

    def test_dry_run_env(self) -> None:
        with patch.dict("os.environ", {"GUANGYA_CLOUD_DRY_RUN": "1"}, clear=False):
            self.assertFalse(cloud_apply_enabled())

    def test_submit_from_result_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = {
                "matched": [
                    {
                        "region": "domestic_leak",
                        "title": "test",
                        "magnets": ["magnet:?xt=urn:btih:deadbeef"],
                        "downloadable": True,
                    },
                ],
            }
            result_path = root / "last_result.json"
            result_path.write_text(json.dumps(result), encoding="utf-8")
            with patch.dict(
                "os.environ",
                {"GUANGYA_CLOUD_DRY_RUN": "1", "GUANGYA_CLOUD_PARENT": "My Pack"},
                clear=False,
            ):
                with patch(
                    "guangya_cloud_daily.resolve_remote_parent_id",
                    return_value="folder-id-123",
                ):
                    ok, total = submit_from_result(
                        result_path,
                        today_only=False,
                        region_filter=True,
                        new_only=False,
                    )
            self.assertEqual(ok, 0)
            self.assertGreaterEqual(total, 0)
            report = json.loads((root / "download_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report.get("provider"), "guangya")


if __name__ == "__main__":
    unittest.main()
