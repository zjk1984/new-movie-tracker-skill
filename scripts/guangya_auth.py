# -*- coding: utf-8 -*-
"""Persist GuangYaPan (光鸭云盘) tokens in the skill directory."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_AUTH_FILE = SKILL_DIR / "guangya_auth.json"
DEFAULT_CLIENT_ID = "aMe-8VSlkrbQXpUR"


def auth_file_path() -> Path:
    return Path(os.environ.get("GUANGYA_AUTH_FILE", DEFAULT_AUTH_FILE))


def load_auth_store() -> dict[str, Any]:
    path = auth_file_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_auth_store(store: dict[str, Any]) -> None:
    path = auth_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_saved_client_id(default: str = DEFAULT_CLIENT_ID) -> str:
    return (load_auth_store().get("client_id") or default).strip() or default


def load_saved_access_token() -> str:
    return (load_auth_store().get("access_token") or "").strip()


def load_saved_refresh_token() -> str:
    return (load_auth_store().get("refresh_token") or "").strip()


def load_saved_device_id() -> str:
    return (load_auth_store().get("device_id") or "").strip()


def save_credentials(
    *,
    client_id: str | None = None,
    access_token: str | None = None,
    refresh_token: str | None = None,
    device_id: str | None = None,
) -> None:
    store = load_auth_store()
    if client_id is not None:
        store["client_id"] = client_id.strip()
    if access_token is not None:
        store["access_token"] = access_token.strip()
    if refresh_token is not None:
        store["refresh_token"] = refresh_token.strip()
    if device_id is not None:
        store["device_id"] = device_id.strip()
    store["updated"] = datetime.now().isoformat(timespec="seconds")
    save_auth_store(store)


def clear_credentials() -> bool:
    path = auth_file_path()
    if not path.exists():
        return False
    path.unlink()
    return True


def resolve_client_id(explicit: str | None = None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    env = (os.environ.get("GUANGYA_CLIENT_ID") or "").strip()
    if env:
        return env
    return load_saved_client_id()


def resolve_access_token(explicit: str | None = None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    env = (os.environ.get("GUANGYA_ACCESS_TOKEN") or "").strip()
    if env:
        return env
    return load_saved_access_token()


def resolve_refresh_token(explicit: str | None = None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    env = (os.environ.get("GUANGYA_REFRESH_TOKEN") or "").strip()
    if env:
        return env
    return load_saved_refresh_token()


def resolve_device_id(explicit: str | None = None) -> str | None:
    if explicit and explicit.strip():
        return explicit.strip()
    env = (os.environ.get("GUANGYA_DEVICE_ID") or "").strip()
    if env:
        return env
    saved = load_saved_device_id()
    return saved or None


def resolve_token(explicit: str | None = None) -> str:
    """Alias for access_token resolution (mirrors PikPak naming in callers)."""
    return resolve_access_token(explicit)


_AUTH_ERROR_MARKERS = (
    "no guangya",
    "no access token",
    "invalid token",
    "token invalid",
    "token expired",
    "unauthorized",
    "unauthenticated",
    "authentication",
    "access_token",
    "invalid_grant",
    "http 401",
    "http 403",
    "refresh token failed",
    "无可用的 refresh_token",
)

_QUOTA_ERROR_MARKERS = (
    "quota",
    "space not enough",
    "not enough storage",
    "storage space",
    "insufficient space",
    "daily limit",
    "create limit",
    "次数",
    "容量",
)


def classify_submit_error(error: str) -> str | None:
    text = (error or "").strip().lower()
    if not text:
        return None
    for marker in _AUTH_ERROR_MARKERS:
        if marker in text:
            return "auth"
    for marker in _QUOTA_ERROR_MARKERS:
        if marker in text:
            return "quota"
    return None


def format_submit_skip_reason(kind: str, detail: str = "") -> str:
    detail = (detail or "").strip().lower().replace(" ", "_")
    if detail:
        return f"{kind}:{detail}"
    return kind


def refresh_access_token(
    refresh_token: str,
    *,
    client_id: str | None = None,
    device_id: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    import requests

    cid = client_id or resolve_client_id()
    did = device_id or resolve_device_id()
    headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": "https://www.guangyapan.com",
        "referer": "https://www.guangyapan.com/",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
        ),
        "x-client-id": cid,
        "x-client-version": "0.0.1",
        "x-action": "401",
    }
    if did:
        headers["x-device-id"] = did
    resp = requests.post(
        "https://account.guangyapan.com/v1/auth/token",
        headers=headers,
        json={
            "client_id": cid,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token.strip(),
        },
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"refresh token failed: HTTP {resp.status_code} {resp.text[:300]}")
    data = resp.json()
    if not data.get("access_token"):
        raise RuntimeError(f"refresh response missing access_token: {data}")
    return data


def _skill_agent_credentials_paths() -> list[Path]:
    """Candidate guangyapan-drive Skill ``credentials.json`` files (newest first)."""
    paths: list[Path] = []
    profile = (os.environ.get("GUANGYAPAN_PROFILE_DIR") or "").strip()
    if profile:
        paths.append(Path(profile) / "account" / "credentials.json")
    state_root = Path(
        os.environ.get("GUANGYAPAN_DRIVE_STATE_ROOT", str(Path.home() / ".guangyapan-drive")),
    )
    agents = state_root / "agents"
    if agents.is_dir():
        for cred in agents.glob("*/account/credentials.json"):
            paths.append(cred)
    # De-dupe, newest mtime first
    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in sorted(set(paths), key=lambda p: p.stat().st_mtime if p.is_file() else 0, reverse=True):
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered


def needs_skill_token_sync() -> bool:
    """True when daily HTTP client should pull tokens from the Skill credential store."""
    if not load_saved_refresh_token():
        return True
    access = load_saved_access_token()
    # Legacy placeholder tokens from early guangya_login (no refresh, 401 on API).
    return access.startswith("TOKEN")


def sync_credentials_from_skill_store(*, force: bool = False) -> bool:
    """Mirror Skill CLI tokens into ``guangya_auth.json`` for ``guangya_download`` HTTP client."""
    if not force and not needs_skill_token_sync() and load_saved_access_token():
        return False
    for path in _skill_agent_credentials_paths():
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        creds = payload.get("credentials") if isinstance(payload, dict) else None
        if not isinstance(creds, dict):
            continue
        access = (creds.get("accessToken") or creds.get("access_token") or "").strip()
        refresh = (creds.get("refreshToken") or creds.get("refresh_token") or "").strip()
        if not access:
            continue
        save_credentials(access_token=access, refresh_token=refresh or None)
        return True
    return False
