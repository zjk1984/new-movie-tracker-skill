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
