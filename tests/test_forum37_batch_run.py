# -*- coding: utf-8
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from forum37_batch_run import (  # noqa: E402
    build_state_after_run,
    resolve_next_start_page,
    save_state,
    state_path,
)


class Forum37BatchRunTests(unittest.TestCase):
    def test_resolve_next_start_page_uses_saved_cursor(self):
        state = {"next_start_page": 970}
        self.assertEqual(resolve_next_start_page(state, initial_page=960), 970)

    def test_resolve_next_start_page_defaults_to_initial(self):
        self.assertEqual(resolve_next_start_page({}, initial_page=960), 960)

    def test_resolve_next_start_page_set_page_override(self):
        state = {"next_start_page": 970}
        self.assertEqual(
            resolve_next_start_page(state, initial_page=960, set_page=960),
            960,
        )

    def test_build_state_after_run_advances_cursor(self):
        out = build_state_after_run(
            forum_url="https://www.sehuatang.org/forum-37-1.html",
            initial_page=960,
            start_page=960,
            max_pages=10,
            previous={"runs_completed": 2},
        )
        self.assertEqual(out["last_start_page"], 960)
        self.assertEqual(out["last_end_page"], 969)
        self.assertEqual(out["next_start_page"], 970)
        self.assertEqual(out["runs_completed"], 3)

    def test_save_and_load_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = state_path(Path(tmp))
            save_state(path, {"next_start_page": 980})
            self.assertEqual(path.read_text(encoding="utf-8").strip().startswith("{"), True)

    @patch("forum37_batch_run.subprocess.call", return_value=0)
    @patch("forum37_batch_run.load_state", return_value={})
    def test_run_batch_passes_batch_mode_and_fetch_workers(self, _load, mock_call):
        from argparse import Namespace

        from forum37_batch_run import run_batch

        with tempfile.TemporaryDirectory() as tmp:
            args = Namespace(
                status=False,
                reset=False,
                output_dir=tmp,
                forum_url="https://www.sehuatang.org/forum-37-1.html",
                initial_page=960,
                max_pages=10,
                set_page=None,
                headless=True,
                scan_only=False,
                feishu=False,
                no_feishu=False,
                fetch_workers=5,
            )
            self.assertEqual(run_batch(args), 0)
        cmd = mock_call.call_args[0][0]
        self.assertIn("--batch-mode", cmd)
        self.assertIn("--fetch-workers", cmd)
        idx = cmd.index("--fetch-workers")
        self.assertEqual(cmd[idx + 1], "5")


if __name__ == "__main__":
    unittest.main()
