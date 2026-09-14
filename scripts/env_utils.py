# -*- coding: utf-8 -*-
"""Shared environment helpers."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SKILL_DIR = Path(__file__).resolve().parent.parent
BEIJING_TZ = ZoneInfo("Asia/Shanghai")
BEIJING_TIME_FMT = "%Y-%m-%d %H:%M:%S"


def load_env_local(skill_dir: Path | None = None) -> None:
    env_path = (skill_dir or SKILL_DIR) / ".env.local"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def beijing_now() -> datetime:
    return datetime.now(BEIJING_TZ)


def beijing_now_iso(*, timespec: str = "seconds") -> str:
    return beijing_now().isoformat(timespec=timespec)


def parse_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        return datetime.fromisoformat(text[:26])
    except ValueError:
        return None


def format_beijing_time(
    value: datetime | str | None,
    *,
    with_label: bool = True,
) -> str:
    """Format a datetime as Asia/Shanghai wall clock for reports."""
    dt = parse_datetime(value)
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=BEIJING_TZ)
    else:
        dt = dt.astimezone(BEIJING_TZ)
    formatted = dt.strftime(BEIJING_TIME_FMT)
    if with_label:
        return f"{formatted} (北京时间)"
    return formatted
