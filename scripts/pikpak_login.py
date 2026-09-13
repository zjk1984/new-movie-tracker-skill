#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Save and manage PikPak token for this skill."""
from __future__ import annotations

import argparse
import getpass
import sys

from pikpak_auth import (
    SKILL_DIR,
    auth_file_path,
    clear_token,
    load_auth_store,
    load_saved_folder,
    resolve_token,
    save_token,
)
from pikpak_download import decode_jwt_payload, list_files


from env_utils import load_env_local as _load_env_local


def cmd_login(args: argparse.Namespace) -> int:
    if args.from_env:
        _load_env_local()
    token = (args.token or "").strip()
    if not token:
        token = (resolve_token() or "").strip()
    if not token:
        token = getpass.getpass("PikPak personal access token: ").strip()
    if not token:
        print("[err] token is required", file=sys.stderr)
        return 1

    folder = (args.folder or "").strip() or None
    try:
        payload = decode_jwt_payload(token)
    except Exception as exc:
        print(f"[err] token does not look like a valid JWT: {exc}", file=sys.stderr)
        return 1

    save_token(token, folder=folder or load_saved_folder())
    sub = payload.get("sub", "")
    print(f"[ok] token saved to {auth_file_path()}")
    if sub:
        print(f"[ok] user id: {sub}")
    folder_name = folder or load_saved_folder()
    if folder_name:
        print(f"[ok] default folder: {folder_name}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    store = load_auth_store()
    path = auth_file_path()
    if not store.get("token") and not resolve_token():
        print("[info] no saved PikPak token")
        print("[hint] run: python scripts/pikpak_login.py login")
        print(f"[hint] or set PIKPAK_TOKEN / save to {path}")
        return 1

    print(f"auth file: {path}")
    if store.get("updated"):
        print(f"updated: {store['updated']}")
    if store.get("folder"):
        print(f"folder: {store['folder']}")
    token = resolve_token()
    if not token:
        print("[err] no token available", file=sys.stderr)
        return 1

    payload: dict = {}
    try:
        payload = decode_jwt_payload(token)
        print(f"user id: {payload.get('sub', '(unknown)')}")
    except Exception as exc:
        print(f"[warn] could not decode token: {exc}")

    if args.check:
        import hashlib

        import requests

        if not payload:
            print("[err] cannot verify token without valid JWT payload", file=sys.stderr)
            return 1
        user_id = payload.get("sub", "")
        device_id = hashlib.md5(user_id.encode()).hexdigest()
        session = requests.Session()
        try:
            files = list_files(session, token, device_id, user_id, limit=1)
            print(f"[ok] token valid ({len(files)} file(s) visible at root)")
        except Exception as exc:
            print(f"[err] token check failed: {exc}", file=sys.stderr)
            return 1
    return 0


def cmd_logout(args: argparse.Namespace) -> int:
    if clear_token():
        print(f"[ok] removed {auth_file_path()}")
        return 0
    print("[info] no saved token to remove")
    return 1


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Manage PikPak token for this skill")
    sub = parser.add_subparsers(dest="command", required=True)

    login = sub.add_parser("login", help="Save personal access token")
    login.add_argument("-t", "--token", default=None, help="Token (avoid on shared shells)")
    login.add_argument(
        "--folder",
        default=None,
        help="Default download folder name (default: My Pack)",
    )
    login.add_argument(
        "--from-env",
        action="store_true",
        help="Import token from PIKPAK_TOKEN or .env.local",
    )
    login.set_defaults(func=cmd_login)

    status = sub.add_parser("status", help="Show saved token info")
    status.add_argument("--check", action="store_true", help="Verify token against PikPak API")
    status.set_defaults(func=cmd_status)

    logout = sub.add_parser("logout", help="Remove saved token")
    logout.set_defaults(func=cmd_logout)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
