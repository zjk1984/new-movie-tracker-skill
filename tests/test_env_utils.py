# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from env_utils import format_beijing_time, parse_datetime  # noqa: E402


class BeijingTimeTests(unittest.TestCase):
    def test_parse_aware_utc_to_beijing(self):
        dt = parse_datetime("2026-09-13T15:08:26+00:00")
        self.assertIsNotNone(dt)
        self.assertEqual(
            format_beijing_time(dt, with_label=False),
            "2026-09-13 23:08:26",
        )

    def test_naive_legacy_utc_converts_to_beijing(self):
        self.assertEqual(
            format_beijing_time("2026-09-13T23:08:26", with_label=False),
            "2026-09-14 07:08:26",
        )

    def test_naive_with_beijing_offset_unchanged(self):
        self.assertEqual(
            format_beijing_time("2026-09-14T07:08:26+08:00", with_label=False),
            "2026-09-14 07:08:26",
        )

    def test_with_label(self):
        text = format_beijing_time(
            datetime(2026, 9, 13, 23, 8, 26, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
        self.assertIn("(北京时间)", text)
        self.assertIn("2026-09-13 23:08:26", text)


if __name__ == "__main__":
    unittest.main()
