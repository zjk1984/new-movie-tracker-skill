# -*- coding: utf-8
from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from custom_run import clamp_max_pages  # noqa: E402


class CustomRunTests(unittest.TestCase):
    def test_clamp_max_pages_caps_at_100(self):
        self.assertEqual(clamp_max_pages(100), 100)
        self.assertEqual(clamp_max_pages(200), 100)

    def test_clamp_max_pages_rejects_zero(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            clamp_max_pages(0)


if __name__ == "__main__":
    unittest.main()
