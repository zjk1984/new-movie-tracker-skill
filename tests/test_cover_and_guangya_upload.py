# -*- coding: utf-8 -*-
from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from guangya_downloads_jav_scrape_lib import upload_sidecar_bytes  # noqa: E402
from pikpak_downloads_jav_scrape_lib import (  # noqa: E402
    fetch_cover_bytes,
    is_jpeg_image,
    is_webp_image,
    normalize_cover_url,
    transcode_cover_bytes_to_jpeg,
    validate_jpeg_cover_bytes,
)


def _sample_webp_bytes() -> bytes:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=4x4",
            "-frames:v",
            "1",
            "-f",
            "webp",
            "pipe:1",
        ],
        capture_output=True,
        check=True,
    )
    return proc.stdout


class CoverValidationTests(unittest.TestCase):
    def test_jpeg_magic(self):
        self.assertTrue(is_jpeg_image(b"\xff\xd8\xff\xe0" + b"x" * 10))
        self.assertFalse(is_jpeg_image(b"GIF89a"))

    def test_rejects_html(self):
        with self.assertRaises(RuntimeError):
            validate_jpeg_cover_bytes(b"<html><body>403</body></html>")

    def test_normalize_protocol_relative(self):
        self.assertEqual(
            normalize_cover_url("//img.example/c.jpg"),
            "https://img.example/c.jpg",
        )

    @patch("pikpak_downloads_jav_scrape_lib.http")
    def test_fetch_cover_validates_jpeg(self, mock_http):
        mock_http.get.return_value.status_code = 200
        mock_http.get.return_value.content = b"\xff\xd8\xff" + b"\x00" * 20
        data = fetch_cover_bytes("https://img.example/x.jpg")
        self.assertTrue(is_jpeg_image(data))
        mock_http.get.assert_called_once()
        _args, kwargs = mock_http.get.call_args
        self.assertIn("Referer", kwargs.get("headers") or {})

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg required")
    def test_transcode_webp_to_jpeg(self):
        webp = _sample_webp_bytes()
        self.assertTrue(is_webp_image(webp))
        jpeg = transcode_cover_bytes_to_jpeg(webp)
        self.assertTrue(is_jpeg_image(jpeg))
        validate_jpeg_cover_bytes(jpeg)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg required")
    @patch("pikpak_downloads_jav_scrape_lib.http")
    def test_fetch_cover_transcodes_webp(self, mock_http):
        webp = _sample_webp_bytes()
        mock_http.get.return_value.status_code = 200
        mock_http.get.return_value.content = webp
        data = fetch_cover_bytes("https://img.example/x.webp")
        self.assertTrue(is_jpeg_image(data))
        validate_jpeg_cover_bytes(data)


class GuangYaUploadNamingTests(unittest.TestCase):
    @patch("guangya_downloads_jav_scrape_lib.upload_local_file")
    def test_upload_uses_intended_remote_basename(self, mock_upload):
        upload_sidecar_bytes(b"nfo", "JUR-832.nfo", "parent-1")
        path = mock_upload.call_args[0][0]
        self.assertEqual(path.name, "JUR-832.nfo")

    @patch("guangya_downloads_jav_scrape_lib.upload_local_file")
    def test_poster_upload_basename(self, mock_upload):
        jpeg = b"\xff\xd8\xff" + b"\x00" * 8
        upload_sidecar_bytes(jpeg, "JUR-832-poster.jpg", "parent-1")
        path = mock_upload.call_args[0][0]
        self.assertEqual(path.name, "JUR-832-poster.jpg")


if __name__ == "__main__":
    unittest.main()
