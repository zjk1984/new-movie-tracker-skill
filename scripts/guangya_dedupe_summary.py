#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge GuangYa dedupe cron pipeline metadata for Feishu (data/guangya_dedupe_last_run.json)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent


def summary_path() -> Path:
    raw = (os.environ.get("GUANGYA_DEDUPE_SUMMARY_JSON") or "data/guangya_dedupe_last_run.json").strip()
    path = Path(raw)
    return path if path.is_absolute() else SKILL_DIR / path


def load_summary() -> dict[str, Any]:
    path = summary_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save_summary(data: dict[str, Any]) -> Path:
    path = summary_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data.setdefault("log_path", "data/guangya_dedupe.log")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def merge_summary(patch: dict[str, Any]) -> Path:
    data = load_summary()
    data.update(patch)
    return save_summary(data)


def main() -> int:
    parser = argparse.ArgumentParser(description="Update guangya_dedupe_last_run.json")
    sub = parser.add_subparsers(dest="cmd", required=True)

    reset = sub.add_parser("reset", help="Remove summary file (start of cron run)")
    reset.set_defaults(func="reset")

    merge = sub.add_parser("merge", help="Merge JSON object from argv or --json")
    merge.add_argument("json_blob", nargs="?", default="{}")
    merge.add_argument("--json", dest="json_opt", default=None)
    merge.set_defaults(func="merge")

    args = parser.parse_args()
    if args.func == "reset":
        path = summary_path()
        if path.is_file():
            path.unlink()
        print(f"[info] reset {path}")
        return 0

    raw = args.json_opt if args.json_opt is not None else args.json_blob
    try:
        patch = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"[err] invalid json: {exc}", file=sys.stderr)
        return 1
    if not isinstance(patch, dict):
        print("[err] expected JSON object", file=sys.stderr)
        return 1
    path = merge_summary(patch)
    print(f"[info] updated {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
