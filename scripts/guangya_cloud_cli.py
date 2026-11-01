#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Invoke guangyapan-drive Skill CLI (``run``, ``login-status``) from Python."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

TERMINAL_BATCH_STATES = frozenset({"SUCCEEDED", "PARTIAL", "FAILED", "STOPPED"})

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
    node = resolve_node_executable()
    node_dir = str(Path(node).parent)
    path = env.get("PATH", "")
    if node_dir and node_dir not in path.split(os.pathsep):
        env["PATH"] = f"{node_dir}{os.pathsep}{path}" if path else node_dir
    return env


@lru_cache(maxsize=1)
def resolve_node_executable() -> str:
    """Node for guangyapan Skill CLI (cron/tmux often lack agent PATH)."""
    override = (os.environ.get("GUANGYAPAN_NODE") or os.environ.get("NODE_BINARY") or "").strip()
    if override and Path(override).is_file():
        return override
    found = shutil.which("node")
    if found:
        return found
    for candidate in (
        "/exec-daemon/node",
        "/usr/bin/node",
        "/usr/local/bin/node",
    ):
        if Path(candidate).is_file():
            return candidate
    raise FileNotFoundError(
        "node not found for guangyapan-drive CLI; set GUANGYAPAN_NODE or install Node.js",
    )


def _base_cmd(*extra: str) -> list[str]:
    root = skill_root()
    return [
        resolve_node_executable(),
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


def batch_status(
    batch_id: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    timeout: float = 120.0,
) -> tuple[int, dict[str, Any], str]:
    run = runner or subprocess.run
    cmd = _base_cmd("status", "--batch-id", batch_id)
    proc = run(
        cmd,
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


def wait_batch_terminal(
    batch_id: str,
    *,
    timeout: float = 600.0,
    poll_interval: float = 1.0,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    """Poll Skill ``status`` until batch reaches a terminal state."""
    deadline = time.monotonic() + max(1.0, timeout)
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        code, data, stderr = batch_status(batch_id, runner=runner)
        last = data
        state = str(data.get("batch_state") or "").strip().upper()
        if state in TERMINAL_BATCH_STATES:
            if state != "SUCCEEDED" or code != 0:
                msg = stderr or data.get("code") or state
                raise RuntimeError(f"GuangYa batch {batch_id!r} ended {state}: {msg}")
            return data
        time.sleep(max(0.2, poll_interval))
    raise TimeoutError(f"GuangYa batch {batch_id!r} did not finish within {timeout}s; last={last!r}")


def delete_remote_files(
    file_ids: list[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    wait_timeout: float = 600.0,
) -> dict[str, Any]:
    """Delete remote files (recycle/trash per GuangYa backend) via Skill ``delete_files``."""
    ids = [str(i).strip() for i in file_ids if str(i).strip()]
    if not ids:
        return {"deleted": 0, "batches": 0}
    total_deleted = 0
    batch_count = 0
    for start in range(0, len(ids), 100):
        chunk = ids[start : start + 100]
        operations = [
            {"id": f"delete-{idx}", "type": "delete_files", "file_ids": [fid]}
            for idx, fid in enumerate(chunk)
        ]
        code, data, stderr = run_operations(operations, runner=runner)
        batch_id = str(data.get("batch_id") or "").strip()
        if not batch_id:
            raise RuntimeError(f"delete_files run missing batch_id: {stderr or data}")
        if code != 0 and not batch_id:
            raise RuntimeError(f"delete_files run failed: {stderr or data}")
        terminal = wait_batch_terminal(batch_id, timeout=wait_timeout, runner=runner)
        batch_count += 1
        for item in (terminal.get("data") or {}).get("items") or terminal.get("items") or []:
            result = item.get("result") or {}
            total_deleted += int(result.get("deleted_count") or 0)
    return {"deleted": total_deleted, "batches": batch_count, "requested": len(ids)}


def upload_local_file(
    local_path: Path | str,
    remote_parent_id: str,
    *,
    operation_id: str = "upload-1",
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    wait_timeout: float = 600.0,
) -> dict[str, Any]:
    """Upload one local file into ``remote_parent_id`` and wait for batch completion."""
    path = Path(local_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"upload source not found: {path}")
    code, data, stderr = run_operations(
        [
            {
                "id": operation_id,
                "type": "upload",
                "local_path": str(path),
                "remote_parent_id": remote_parent_id,
            },
        ],
        runner=runner,
    )
    batch_id = str(data.get("batch_id") or "").strip()
    if not batch_id:
        raise RuntimeError(f"upload run missing batch_id: {stderr or data}")
    if code != 0 and not batch_id:
        raise RuntimeError(f"upload run failed: {stderr or data}")
    return wait_batch_terminal(batch_id, timeout=wait_timeout, runner=runner)
