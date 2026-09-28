# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from daily_run import run_scan


class DailyRunGatingTests(unittest.TestCase):
    @patch("subprocess.call", return_value=0)
    def test_run_scan_defaults_to_gate_before_fetch(self, mock_call):
        args = argparse.Namespace(
            days=2,
            max_pages=10,
            urls=["https://example.org/forum-142-1.html"],
            headless=True,
            serial=False,
            list_workers=3,
            fetch_workers=4,
            gate_before_fetch=True,
            batch_mode=False,
        )
        out_dir = Path("/tmp/fake-output")
        rc = run_scan(args, out_dir)
        self.assertEqual(rc, 0)
        mock_call.assert_called_once()
        cmd = mock_call.call_args[0][0]
        self.assertIn("--gate-before-fetch", cmd)
        self.assertNotIn("--batch-mode", cmd)

    @patch("subprocess.call", return_value=0)
    def test_run_scan_disables_gate_before_fetch_when_false(self, mock_call):
        args = argparse.Namespace(
            days=2,
            max_pages=10,
            urls=["https://example.org/forum-142-1.html"],
            headless=True,
            serial=False,
            list_workers=3,
            fetch_workers=4,
            gate_before_fetch=False,
            batch_mode=True,
        )
        out_dir = Path("/tmp/fake-output")
        rc = run_scan(args, out_dir)
        self.assertEqual(rc, 0)
        cmd = mock_call.call_args[0][0]
        self.assertNotIn("--gate-before-fetch", cmd)
        self.assertIn("--batch-mode", cmd)


if __name__ == "__main__":
    unittest.main()
