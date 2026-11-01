# -*- coding: utf-8 -*-
"""Helpers for PikPak downloads JAV → Jellyfin sidecar scrape."""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Callable, Iterator

from content_filter import classify_region
from javdb_client import JAV_REPORT_REGIONS, JavDBClient
from jellyfin_nfo import (
    canonical_av_number,
    is_video_filename,
    merge_scrape_metadata,
    metadata_sidecar_names,
)
from pikpak_downloads_dedupe_lib import (
    DEFAULT_FOLDER,
    av_number_for_jav_dedupe,
    pseudo_as_jav_from_env,
)

try:
    from curl_cffi import requests as http
except ImportError:
    http = None  # type: ignore[assignment,misc]


def scrape_delay_seconds() -> float:
    raw = os.environ.get("JAVDB_SCRAPE_DELAY", "1.5").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 1.5


def downloads_folder_from_env(default: str = DEFAULT_FOLDER) -> str:
    return (os.environ.get("PIKPAK_DOWNLOADS_FOLDER") or default).strip() or default


def is_jav_video_row(name: str, *, pseudo_as_jav: bool | None = None) -> tuple[bool, str | None]:
    pseudo = pseudo_as_jav if pseudo_as_jav is not None else pseudo_as_jav_from_env(None)
    av = av_number_for_jav_dedupe(name, pseudo_as_jav=pseudo)
    if not av:
        return False, None
    region = classify_region({"title": name, "av_number": av})
    if region not in JAV_REPORT_REGIONS:
        return False, av
    return True, av


def iter_jav_video_files(
    list_children: Callable[..., list[dict]],
    session: Any,
    token: str,
    device_id: str,
    user_id: str,
    downloads_parent_id: str,
    *,
    recursive: bool = True,
) -> Iterator[tuple[dict[str, Any], str]]:
    """Yield (completed video file row, parent_id) under ``downloads``."""
    queue: deque[str] = deque([downloads_parent_id])
    while queue:
        parent_id = queue.popleft()
        rows = list_children(
            session,
            token,
            device_id,
            user_id,
            parent_id=parent_id,
            complete_files_only=True,
        )
        for row in rows:
            kind = row.get("kind")
            if kind == "drive#folder":
                if recursive:
                    folder_id = str(row.get("id") or "")
                    if folder_id:
                        queue.append(folder_id)
                continue
            if kind != "drive#file":
                continue
            if row.get("phase") != "PHASE_TYPE_COMPLETE":
                continue
            name = str(row.get("name") or "")
            if not is_video_filename(name):
                continue
            ok, _av = is_jav_video_row(name)
            if not ok:
                continue
            yield row, parent_id


def group_videos_by_av(
    videos: list[tuple[dict[str, Any], str]],
    *,
    pseudo_as_jav: bool | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Group scanned videos by 番号 (one metadata folder per 番号)."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row, video_parent_id in videos:
        name = str(row.get("name") or "")
        ok, av = is_jav_video_row(name, pseudo_as_jav=pseudo_as_jav)
        if not ok or not av:
            continue
        groups[av.upper()].append(
            {
                "video_id": row.get("id"),
                "video_name": name,
                "video_parent_id": video_parent_id,
            },
        )
    return dict(groups)


def sibling_name_set(
    list_children: Callable[..., list[dict]],
    session: Any,
    token: str,
    device_id: str,
    user_id: str,
    parent_id: str,
) -> set[str]:
    names: set[str] = set()
    for row in list_children(
        session,
        token,
        device_id,
        user_id,
        parent_id=parent_id,
        complete_files_only=False,
    ):
        name = str(row.get("name") or "")
        if name:
            names.add(name)
    return names


JPEG_MAGIC = b"\xff\xd8\xff"


def normalize_cover_url(url: str) -> str:
    u = (url or "").strip()
    if u.startswith("//"):
        return f"https:{u}"
    return u


def is_jpeg_image(data: bytes) -> bool:
    return len(data) >= 3 and data[:3] == JPEG_MAGIC


def looks_like_html_body(data: bytes) -> bool:
    head = data[:512].lstrip().lower()
    return head.startswith(b"<!doctype") or head.startswith(b"<html") or head.startswith(b"<")


def validate_jpeg_cover_bytes(data: bytes) -> None:
    if not data:
        raise RuntimeError("empty cover body")
    if looks_like_html_body(data):
        raise RuntimeError("cover response looks like HTML, not a JPEG")
    if not is_jpeg_image(data):
        magic = data[:8].hex() if data else ""
        raise RuntimeError(f"cover is not a valid JPEG (expected ff d8 ff; got {magic})")


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def is_webp_image(data: bytes) -> bool:
    return len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP"


def is_png_image(data: bytes) -> bool:
    return len(data) >= len(PNG_MAGIC) and data[: len(PNG_MAGIC)] == PNG_MAGIC


def is_avif_image(data: bytes) -> bool:
    if len(data) < 12:
        return False
    if data[4:8] != b"ftyp":
        return False
    brand = data[8:12]
    return brand in (b"avif", b"avis", b"mif1") or b"avif" in data[:64]


def cover_bytes_input_suffix(data: bytes) -> str:
    if is_webp_image(data):
        return ".webp"
    if is_png_image(data):
        return ".png"
    if is_avif_image(data):
        return ".avif"
    return ".img"


def _transcode_cover_with_pillow(data: bytes) -> bytes | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(io.BytesIO(data)) as img:
            rgb = img.convert("RGB")
            out = io.BytesIO()
            rgb.save(out, format="JPEG", quality=90, optimize=True)
            return out.getvalue()
    except Exception:
        return None


def _transcode_cover_with_ffmpeg(data: bytes) -> bytes:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("cover transcode requires Pillow or ffmpeg on PATH")
    suffix = cover_bytes_input_suffix(data)
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / f"cover_in{suffix}"
        dst = Path(tmpdir) / "cover_out.jpg"
        src.write_bytes(data)
        proc = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(src),
                "-frames:v",
                "1",
                "-f",
                "image2",
                "-vcodec",
                "mjpeg",
                "-q:v",
                "2",
                str(dst),
            ],
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"ffmpeg cover transcode failed: {err or proc.returncode}")
        out = dst.read_bytes()
        if not out:
            raise RuntimeError("ffmpeg cover transcode produced empty output")
        return out


def transcode_cover_bytes_to_jpeg(data: bytes) -> bytes:
    """Convert WebP/AVIF/PNG (etc.) cover bytes to JPEG."""
    if is_jpeg_image(data):
        return data
    if looks_like_html_body(data):
        raise RuntimeError("cover response looks like HTML, not an image")
    via_pillow = _transcode_cover_with_pillow(data)
    if via_pillow and is_jpeg_image(via_pillow):
        return via_pillow
    return _transcode_cover_with_ffmpeg(data)


def ensure_jpeg_cover_bytes(data: bytes) -> bytes:
    if not data:
        raise RuntimeError("empty cover body")
    if looks_like_html_body(data):
        raise RuntimeError("cover response looks like HTML, not a JPEG")
    if not is_jpeg_image(data):
        data = transcode_cover_bytes_to_jpeg(data)
    validate_jpeg_cover_bytes(data)
    return data


def fetch_cover_bytes(url: str, *, timeout: float = 30.0) -> bytes:
    url = normalize_cover_url(url)
    if not url:
        raise ValueError("empty cover url")
    if http is None:
        raise ImportError("cover download requires curl_cffi")
    headers = {"Referer": "https://javdb.com/"}
    resp = http.get(url, impersonate="chrome120", timeout=timeout, headers=headers)
    if resp.status_code >= 400:
        raise RuntimeError(f"cover HTTP {resp.status_code}")
    return ensure_jpeg_cover_bytes(resp.content)


def lookup_scrape_metadata(
    client: JavDBClient,
    number: str,
    *,
    sleep_fn: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    info = client.lookup(number, fetch_magnets=False, exact=True)
    delay = scrape_delay_seconds()
    if sleep_fn and delay > 0:
        sleep_fn(delay)
    movie_id = str(info.get("javdb_id") or "")
    detail: dict[str, Any] = {}
    if movie_id:
        detail = client.movie_detail(movie_id)
        if sleep_fn and delay > 0:
            sleep_fn(delay)
    return merge_scrape_metadata(info, detail)


def plan_sidecars_for_av(
    av_number: str,
    downloads_parent_id: str,
    *,
    existing_names: set[str],
    include_fanart: bool,
) -> dict[str, Any]:
    sidecars = metadata_sidecar_names(av_number, include_fanart=include_fanart)
    return {
        "av_number": canonical_av_number(av_number),
        "downloads_parent_id": downloads_parent_id,
        "sidecars": sidecars,
        "needs_nfo": sidecars["nfo"] not in existing_names,
        "needs_poster": sidecars["poster"] not in existing_names,
        "needs_fanart": include_fanart and sidecars.get("fanart", "") not in existing_names,
    }
