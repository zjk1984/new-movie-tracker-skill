#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Invoke guangyapan-drive Skill CLI (``run``, ``login-status``) from Python."""
from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any, Callable

DEFAULT_SKILL_ROOT = Path("/cursor/stores/user/skills/guangyapan-drive")
DEFAULT_PROFILE_DIR = Path("/cursor/stores/user/guangyapan-cursor-profile")
DEFAULT_AGENT_NAME = "Cursor"


def skill_root() -> Path:
    raw = os.environ.get("GUANGYAPAN_SKILL_ROOT", "").strip()
    return Path(raw) if raw else DEFAULT_SKILL_ROOT


def profile_dir() -> Path:
    raw = os.environ.get("GUANGYAPAN_PROFILE_DIR", "").strip()
    return Path(raw) if raw else DEFAULT_PROFILE_DIR


def agent_name() -> str:
    return (os.environ.get("GUANGYAPAN_AGENT_NAME") or DEFAULT_AGENT_NAME).strip() or DEFAULT_AGENT_NAME


def cli_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("GUANGYAPAN_DRIVE_LOGIN_MODE", "device")
    return env


def _base_cmd(*extra: str) -> list[str]:
    root = skill_root()
    return [
        "node",
        str(root / "bin" / "guangyapan.mjs"),
        *extra,
        "--agent-name",
        agent_name(),
        "--agent-profile-dir",
        str(profile_dir()),
    ]


def parse_cli_json(stdout: str) -> dict[str, Any]:
    text = (stdout or "").strip()
    if not text:
        return {}
    return json.loads(text)


def run_command(
    command: str,
    *,
    stdin_json: dict[str, Any] | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    timeout: float = 120.0,
) -> tuple[int, dict[str, Any], str]:
    """Run one Skill CLI command; return (exit_code, parsed_json, stderr)."""
    cmd = _base_cmd(command)
    run = runner or subprocess.run
    proc = run(
        cmd,
        input=json.dumps(stdin_json) if stdin_json is not None else None,
        capture_output=True,
        text=True,
        cwd=str(skill_root()),
        env=cli_env(),
        timeout=timeout,
        check=False,
    )
    try:
        payload = parse_cli_json(proc.stdout)
    except json.JSONDecodeError:
        payload = {"raw_stdout": proc.stdout, "parse_error": True}
    return proc.returncode, payload, proc.stderr or ""


def login_status(
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> tuple[int, dict[str, Any], str]:
    return run_command("login-status", runner=runner)


def run_operations(
    operations: list[dict[str, Any]],
    *,
    request_id: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> tuple[int, dict[str, Any], str]:
    payload = {
        "version": 1,
        "request_id": request_id or str(uuid.uuid4()),
        "operations": operations,
    }
    return run_command("run", stdin_json=payload, runner=runner)


def list_root_directories(
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> list[dict[str, Any]]:
    code, data, _stderr = run_operations(
        [{"id": "list-root", "type": "list", "remote_parent_id": ""}],
        runner=runner,
    )
    if code != 0:
        return []
    items = data.get("data", {}).get("items") or []
    if not items:
        return []
    result = (items[0].get("result") or {}) if items else {}
    return list(result.get("items") or [])


def find_directory_id(
    name: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> str | None:
    want = (name or "").strip()
    if not want:
        return None
    for row in list_root_directories(runner=runner):
        if row.get("type") == "directory" and (row.get("name") or "") == want:
            rid = str(row.get("id") or "").strip()
            return rid or None
    return None
