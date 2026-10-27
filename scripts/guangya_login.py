#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Save and manage GuangYaPan tokens for offline magnet download."""
from __future__ import annotations

import argparse
import getpass
import sys

from env_utils import load_env_local as _load_env_local
from guangya_auth import (
    auth_file_path,
    clear_credentials,
    load_auth_store,
    resolve_access_token,
    resolve_client_id,
    resolve_device_id,
    resolve_refresh_token,
    save_credentials,
)


def cmd_login(args: argparse.Namespace) -> int:
    if args.from_env:
        _load_env_local()

    client_id = (args.client_id or resolve_client_id()).strip()
    access_token = (args.access_token or resolve_access_token()).strip()
    refresh_token = (args.refresh_token or resolve_refresh_token()).strip()
    device_id = (args.device_id or resolve_device_id() or "").strip()

    if not access_token:
        access_token = getpass.getpass("GuangYa access_token: ").strip()
    if not refresh_token:
        refresh_token = getpass.getpass("GuangYa refresh_token: ").strip()

    if not access_token:
        print("[err] access_token is required", file=sys.stderr)
        return 1

    save_credentials(
        client_id=client_id,
        access_token=access_token,
        refresh_token=refresh_token or None,
        device_id=device_id or None,
    )
    print(f"[ok] credentials saved to {auth_file_path()}")
    print(f"[ok] client_id: {client_id}")
    if refresh_token:
        print("[ok] refresh_token saved")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    store = load_auth_store()
    path = auth_file_path()
    token = resolve_access_token()
    if not token and not store:
        print("[info] no saved GuangYa credentials")
        print("[hint] run: python scripts/guangya_login.py login")
        print(f"[hint] or set GUANGYA_ACCESS_TOKEN / save to {path}")
        return 1

    print(f"auth file: {path}")
    print(f"client_id: {resolve_client_id()}")
    if store.get("updated"):
        print(f"updated: {store['updated']}")
    if store.get("device_id"):
        print(f"device_id: {store['device_id']}")
    if resolve_refresh_token():
        print("refresh_token: (set)")
    else:
        print("[warn] no refresh_token; token expiry may require manual re-login")

    if not token:
        print("[err] no access_token available", file=sys.stderr)
        return 1

    if args.check:
        try:
            from guangya_download import build_client, persist_client_tokens

            client = build_client()
            try:
                info = client.user_info()
                persist_client_tokens(client)
            finally:
                client.close()
            name = info.get("nickname") or info.get("name") or info.get("phone") or "(unknown)"
            print(f"[ok] API ping OK — user: {name}")
        except Exception as exc:
            print(f"[err] API check failed: {exc}", file=sys.stderr)
            print(
                "[hint] 重新在光鸭网页登录后复制 access_token / refresh_token，"
                "执行 `python scripts/guangya_login.py login`",
                file=sys.stderr,
            )
            return 1
    return 0


def cmd_clear(args: argparse.Namespace) -> int:
    if clear_credentials():
        print(f"[ok] removed {auth_file_path()}")
        return 0
    print("[info] no saved credentials to remove")
    return 1


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Manage GuangYaPan tokens for this skill")
    sub = parser.add_subparsers(dest="command", required=True)

    login = sub.add_parser("login", help="Save client_id and tokens")
    login.add_argument("--client-id", default=None, help="OAuth client_id (default: built-in)")
    login.add_argument("-t", "--access-token", default=None, help="Access token")
    login.add_argument("-r", "--refresh-token", default=None, help="Refresh token")
    login.add_argument("--device-id", default=None, help="Stable device id (optional)")
    login.add_argument(
        "--from-env",
        action="store_true",
        help="Import from GUANGYA_* env vars or .env.local",
    )
    login.set_defaults(func=cmd_login)

    status = sub.add_parser("status", help="Show saved credential info")
    status.add_argument("--check", action="store_true", help="Verify token against GuangYa API")
    status.set_defaults(func=cmd_status)

    clear = sub.add_parser("clear", help="Remove saved credentials")
    clear.set_defaults(func=cmd_clear)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
