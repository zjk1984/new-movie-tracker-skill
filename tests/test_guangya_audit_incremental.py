# -*- coding: utf-8 -*-
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from guangya_audit_incremental import increment_report


class GuangyaAuditIncrementalTests(unittest.TestCase):
    def test_baseline_init_no_new_entries(self) -> None:
        report = {
            "guangya_downloads_folder_id": "gy1",
            "guangya_titles_by_av": {"ABF-001": "abf-001.mp4"},
            "counts": {},
            "pikpak_file_links": [],
        }
        current = {
            "f1": {"guangya_file_id": "f1", "name": "abf-001.mp4", "av_number": "ABF-001", "size": 1},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            with mock.patch("guangya_audit_incremental.login_status", return_value=(0, {"data": {"logged_in": True}}, "")):
                with mock.patch("guangya_audit_incremental._current_downloads_videos", return_value=current):
                    with mock.patch("guangya_audit_incremental.walk_guangya_files", return_value=[{"type": "file"}]):
                        with mock.patch("guangya_audit_incremental._resolve_pikpak_session", side_effect=RuntimeError("no pikpak")):
                            result = increment_report(path)
            self.assertEqual(result["added_this_run"], 0)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["guangya_downloads_snapshot"]["file_ids"], ["f1"])
            self.assertEqual(data.get("guangya_new_entries"), [])

    def test_detects_new_file(self) -> None:
        report = {
            "guangya_downloads_folder_id": "gy1",
            "guangya_titles_by_av": {"ABF-001": "abf-001.mp4"},
            "guangya_downloads_snapshot": {"file_ids": ["f1"], "updated_at_utc": "2026-01-01T00:00:00+00:00"},
            "guangya_new_entries": [],
            "counts": {},
            "pikpak_file_links": [{"av_number": "ABF-002", "url": "magnet:?xt=urn:btih:abc"}],
        }
        current = {
            "f1": {"guangya_file_id": "f1", "name": "abf-001.mp4", "av_number": "ABF-001", "size": 1},
            "f2": {"guangya_file_id": "f2", "name": "abf-002.mp4", "av_number": "ABF-002", "size": 2},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            with mock.patch("guangya_audit_incremental.login_status", return_value=(0, {"data": {"logged_in": True}}, "")):
                with mock.patch("guangya_audit_incremental._current_downloads_videos", return_value=current):
                    with mock.patch("guangya_audit_incremental.walk_guangya_files", return_value=[{}]):
                        with mock.patch("guangya_audit_incremental._resolve_pikpak_session", side_effect=RuntimeError("no pikpak")):
                            with mock.patch("guangya_audit_incremental.JavDBClient"):
                                result = increment_report(path)
            self.assertEqual(result["added_this_run"], 1)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(data["guangya_new_entries"]), 1)
            self.assertEqual(data["guangya_new_entries"][0]["url"], "magnet:?xt=urn:btih:abc")
            self.assertEqual(data["guangya_new_entries"][0]["link_source"], "pikpak_report_cache")


if __name__ == "__main__":
    unittest.main()
