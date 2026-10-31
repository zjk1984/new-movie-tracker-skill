# -*- coding: utf-8
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from guangya_cloud_submit_lib import (  # noqa: E402
    cloud_collection_add_operations,
    enumerate_av_numbers_from_files,
    load_matched_by_av,
    mark_state_submitted,
    resolve_submit_row_for_av,
    state_has_submission,
    submit_rows_to_guangya,
    uri_supported_by_guangya,
)


class UriSupportedTests(unittest.TestCase):
    def test_accepts_magnet_and_ed2k(self) -> None:
        self.assertTrue(uri_supported_by_guangya("magnet:?xt=urn:btih:abc"))
        self.assertTrue(uri_supported_by_guangya("ed2k://|file|a|1|hash|/"))
        self.assertFalse(uri_supported_by_guangya("pikpak://a|1|hash"))


class EnumerateAvTests(unittest.TestCase):
    def test_extracts_from_filenames(self) -> None:
        files = [
            {
                "kind": "drive#file",
                "phase": "PHASE_TYPE_COMPLETE",
                "name": "SSIS-001-C.mp4",
            },
            {
                "kind": "drive#file",
                "phase": "PHASE_TYPE_COMPLETE",
                "name": "SSIS-001-UC.mkv",
            },
            {"kind": "drive#folder", "name": "nested"},
        ]
        av_map = enumerate_av_numbers_from_files(files, pseudo_as_jav=True)
        self.assertIn("SSIS-001", av_map)


class StateDedupeTests(unittest.TestCase):
    def test_by_av_and_uri(self) -> None:
        state = {"uris": {}, "av_numbers": {}}
        mark_state_submitted(state, "SSIS-001", "magnet:?xt=urn:btih:deadbeef")
        self.assertTrue(state_has_submission(state, "SSIS-001", "magnet:?xt=urn:btih:other"))
        self.assertTrue(
            state_has_submission(state, "OTHER", "magnet:?xt=urn:btih:deadbeef"),
        )


class ResolveSubmitRowTests(unittest.TestCase):
    def test_javdb_fallback_when_no_scan_item(self) -> None:
        mock_client = MagicMock()
        mock_client.lookup.return_value = {
            "number": "SSIS-001",
            "query_status": "ok",
            "score": 4.5,
            "content_type": "jav_censored",
            "best_magnet": "magnet:?xt=urn:btih:javdbbest",
            "magnets": ["magnet:?xt=urn:btih:javdbbest"],
            "magnet_status": "available",
        }
        with patch("guangya_cloud_submit_lib.is_submit_eligible", return_value=True):
            with patch("guangya_cloud_submit_lib.apply_region_filter", return_value=True):
                row, reason, source = resolve_submit_row_for_av(
                    "SSIS-001",
                    representative_name="SSIS-001-C.mp4",
                    scan_item=None,
                    javdb_client=mock_client,
                    region_filter=True,
                    javdb_score_gate=True,
                )
        self.assertFalse(reason)
        self.assertEqual(source, "javdb")
        assert row is not None
        self.assertTrue(row["uri"].startswith("magnet:"))

    def test_scan_item_preferred(self) -> None:
        scan_item = {
            "av_number": "IPX-100",
            "title": "[有码] IPX-100 test",
            "magnets": ["magnet:?xt=urn:btih:forum111"],
        }
        with patch("guangya_cloud_submit_lib.is_submit_eligible", return_value=True):
            with patch("guangya_cloud_submit_lib.apply_region_filter", return_value=True):
                row, reason, source = resolve_submit_row_for_av(
                    "IPX-100",
                    scan_item=scan_item,
                    javdb_client=None,
                    javdb_score_gate=False,
                )
        self.assertEqual(source, "scan")
        assert row is not None
        self.assertIn("forum111", row["uri"])


class MatchedByAvTests(unittest.TestCase):
    def test_loads_scan_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "last_result.json"
            path.write_text(
                json.dumps({
                    "matched": [
                        {"av_number": "ABC-123", "title": "t", "magnets": ["magnet:?xt=urn:btih:x"]},
                    ],
                }),
                encoding="utf-8",
            )
            by_av = load_matched_by_av(path)
            self.assertIn("ABC-123", by_av)


class CloudAddOpsTests(unittest.TestCase):
    def test_builds_operations(self) -> None:
        ops = cloud_collection_add_operations(
            [{"uri": "magnet:?xt=urn:btih:a", "av_number": "A", "name": "A"}],
            "parent123",
        )
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["type"], "cloud_collection_add")
        self.assertEqual(ops[0]["remote_parent_id"], "parent123")


class SubmitRowsCliMockTests(unittest.TestCase):
    def test_submit_calls_runner(self) -> None:
        fake_response = {
            "data": {
                "items": [
                    {
                        "operation_id": "add-1",
                        "result": {"task_id": "task-99"},
                    },
                ],
            },
        }

        def fake_runner(*_args, **_kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = json.dumps(fake_response)
            proc.stderr = ""
            return proc

        with patch("guangya_cloud_submit_lib.run_operations", side_effect=lambda ops, **kw: (0, fake_response, "")):
            out = submit_rows_to_guangya(
                [{"uri": "magnet:?xt=urn:btih:z", "av_number": "Z"}],
                remote_parent_id="folder-id",
            )
        self.assertEqual(out["submitted"], 1)
        self.assertEqual(out["results"][0]["task_id"], "task-99")


if __name__ == "__main__":
    unittest.main()
