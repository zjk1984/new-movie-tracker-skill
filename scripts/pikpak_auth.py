# -*- coding: utf-8 -*-
"""Persist PikPak token in the skill directory (like javdb_auth.json)."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_AUTH_FILE = SKILL_DIR / "pikpak_auth.json"


def auth_file_path() -> Path:
    return Path(os.environ.get("PIKPAK_AUTH_FILE", DEFAULT_AUTH_FILE))


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


def load_saved_token() -> str:
    return (load_auth_store().get("token") or "").strip()


def load_saved_folder(default: str = "My Pack") -> str:
    return (load_auth_store().get("folder") or default).strip() or default


def save_token(token: str, *, folder: str | None = None) -> None:
    store = load_auth_store()
    store["token"] = token.strip()
    store["updated"] = datetime.now().isoformat(timespec="seconds")
    if folder is not None:
        store["folder"] = folder.strip()
    save_auth_store(store)


def clear_token() -> bool:
    path = auth_file_path()
    if not path.exists():
        return False
    path.unlink()
    return True


def resolve_token(explicit: str | None = None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    env = (os.environ.get("PIKPAK_TOKEN") or "").strip()
    if env:
        return env
    return load_saved_token()


def resolve_folder(explicit: str | None = None, default: str = "My Pack") -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    env = (os.environ.get("PIKPAK_FOLDER") or "").strip()
    if env:
        return env
    saved = load_saved_folder(default)
    return saved or default


_AUTH_ERROR_MARKERS = (
    "no pikpak token",
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
    "invalid jwt",
    "does not look like a valid jwt",
)

_QUOTA_ERROR_MARKERS = (
    "file_space_not_enough",
    "storage space is not enough",
    "not enough storage",
    "task_daily_create_limit",
    "daily create limit",
    "daily download limit",
    "free usage today",
    "free transfers has been used up",
    "quota",
    "space not enough",
    "insufficient space",
    "insufficient quota",
)


def classify_submit_error(error: str) -> str | None:
    """Return ``auth``, ``quota``, or None for a PikPak submit error message."""
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


def is_auth_or_quota_error(error: str) -> bool:
    return classify_submit_error(error) is not None


def inspect_jwt_token(token: str) -> dict[str, Any]:
    """Inspect a PikPak JWT token, returning payload, exp, validity status, and human tips."""
    import base64
    import time
    from datetime import datetime, timezone

    info: dict[str, Any] = {
        "valid_jwt": False,
        "sub": "",
        "exp": None,
        "exp_iso": "",
        "is_expired": False,
        "seconds_left": None,
        "status": "unknown",
        "message": "",
    }
    if not token or not token.strip():
        info["status"] = "empty"
        info["message"] = "未提供 Token"
        return info

    parts = token.strip().split(".")
    if len(parts) != 3:
        info["status"] = "malformed"
        info["message"] = "Token 格式不正确（非标准 3 段 JWT 格式）"
        return info

    try:
        payload_b64 = parts[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        info["valid_jwt"] = True
        info["payload"] = payload
        info["sub"] = str(payload.get("sub") or "")
        exp = payload.get("exp")
        if exp is not None:
            exp_int = int(exp)
            info["exp"] = exp_int
            exp_dt = datetime.fromtimestamp(exp_int, tz=timezone.utc).astimezone()
            info["exp_iso"] = exp_dt.isoformat(timespec="seconds")
            now = int(time.time())
            diff = exp_int - now
            info["seconds_left"] = diff
            if diff <= 0:
                info["is_expired"] = True
                info["status"] = "expired"
                info["message"] = (
                    f"Token 已于 {info['exp_iso']} 过期（过期 {-diff} 秒）。"
                    "注意：PikPak 网页/App 的 Access Token 有效期通常仅数小时至数天，"
                    "即使云盘空间配额充足，过期后 API 依然会返回 401 Unauthorized。"
                    "请重新登录获取最新 Token。"
                )
            else:
                info["status"] = "active"
                hours = diff // 3600
                mins = (diff % 3600) // 60
                info["message"] = f"Token 有效，剩余时间约 {hours} 小时 {mins} 分钟（到期时间: {info['exp_iso']}）。"
        else:
            info["status"] = "no_exp"
            info["message"] = "Token 结构合法但无 exp 过期字段。"
    except Exception as exc:
        info["status"] = "decode_error"
        info["message"] = f"Token 解码失败: {exc}"

    return info


def refresh_access_token(
    refresh_token: str,
    *,
    client_id: str = "YUMx5nI8ZU8Ap8pm",
    user_host: str = "https://user.mypikpak.com",
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Exchange a PikPak refresh_token for a new access_token."""
    import requests

    url = f"{user_host.rstrip('/')}/v1/auth/token"
    body = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token.strip(),
    }
    resp = requests.post(url, json=body, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"refresh token failed: HTTP {resp.status_code} {resp.text[:300]}")
    data = resp.json()
    new_access = data.get("access_token")
    if not new_access:
        raise RuntimeError(f"refresh response missing access_token: {data}")
    return data


def format_submit_skip_reason(kind: str, detail: str = "") -> str:
    """Build a stable ``submit_skip_reason`` value for download reports."""
    detail = (detail or "").strip().lower().replace(" ", "_")
    if detail:
        return f"{kind}:{detail}"
    return kind
