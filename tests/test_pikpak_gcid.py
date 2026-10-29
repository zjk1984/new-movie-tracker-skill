# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from pikpak_download import calc_gcid  # noqa: E402


def _reference_gcid(data: bytes) -> str:
    size = len(data)
    psize = 0x40000
    while size / psize > 0x200 and psize < 0x200000:
        psize <<= 1
    h = hashlib.sha1()
    offset = 0
    while offset < size:
        chunk = data[offset : offset + psize]
        h.update(hashlib.sha1(chunk).digest())
        offset += psize
    return h.hexdigest().upper()


class GcidTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(calc_gcid(b""), _reference_gcid(b""))

    def test_small_payload(self):
        data = b"hello jellyfin nfo"
        self.assertEqual(calc_gcid(data), _reference_gcid(data))


if __name__ == "__main__":
    unittest.main()
