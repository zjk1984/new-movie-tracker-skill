#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Log in to JavDB and persist token for other scripts."""
from __future__ import annotations

import argparse
import getpass
import sys

from javdb_client import (
    JavDBClient,
    _any_int,
    _any_str,
    auth_file_path,
    load_auth_store,
    remove_auth_account,
    upsert_auth_account,
)


def cmd_login(args: argparse.Namespace) -> int:
    username = (args.username or "").strip()
    password = args.password or ""
    if not username:
        username = input("JavDB username/email: ").strip()
    if not password:
        password = getpass.getpass("JavDB password: ")
    if not username or not password:
        print("[err] username and password are required", file=sys.stderr)
        return 1

    client = JavDBClient(host=args.host, use_saved_token=False)
    try:
        token = client.login(username, password)
        profile = client.check_auth()
    except Exception as exc:
        print(f"[err] login failed: {exc}", file=sys.stderr)
        return 1

    display_name = _any_str(profile.get("username") or profile.get("name") or username)
    user_id = _any_int(profile.get("id"))
    upsert_auth_account(
        username=display_name,
        token=token,
        user_id=user_id or None,
        password=password if args.save_password else None,
        set_default=not args.no_default,
    )
    print(f"[ok] logged in as {display_name}" + (f" (id={user_id})" if user_id else ""))
    print(f"[ok] token saved to {auth_file_path()}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    store = load_auth_store()
    accounts = store.get("accounts") or []
    if not accounts:
        print("[info] no saved JavDB account")
        print(f"[hint] run: python scripts/javdb_login.py login")
        return 1

    default_user = store.get("default_username") or ""
    print(f"auth file: {auth_file_path()}")
    print(f"default: {default_user or '(none)'}")
    for account in accounts:
        if not isinstance(account, dict):
            continue
        username = _any_str(account.get("username"))
        marker = " *" if username == default_user else ""
        updated = _any_str(account.get("updated"))
        user_id = account.get("user_id")
        suffix = f", id={user_id}" if user_id else ""
        print(f"  - {username}{suffix}{marker}" + (f" (updated {updated})" if updated else ""))

    if args.check:
        client = JavDBClient(host=args.host)
        if not client.token:
            print("[err] no token available", file=sys.stderr)
            return 1
        try:
            profile = client.check_auth()
        except Exception as exc:
            print(f"[err] token invalid: {exc}", file=sys.stderr)
            return 1
        name = _any_str(profile.get("username") or profile.get("name"))
        print(f"[ok] token valid for {name or default_user}")
    return 0


def cmd_logout(args: argparse.Namespace) -> int:
    username = (args.username or "").strip() or None
    if remove_auth_account(username):
        target = username or "default account"
        print(f"[ok] removed {target} from {auth_file_path()}")
        return 0
    print("[info] no matching account to remove")
    return 1


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Manage JavDB login for this skill")
    parser.add_argument("--host", default=None, help="JavDB API host")
    sub = parser.add_subparsers(dest="command", required=True)

    login = sub.add_parser("login", help="Log in and save token")
    login.add_argument("-u", "--username", default=None, help="Username or email")
    login.add_argument("-p", "--password", default=None, help="Password (avoid on shared shells)")
    login.add_argument(
        "--save-password",
        action="store_true",
        help="Also save password locally for future re-login (stored in plaintext)",
    )
    login.add_argument(
        "--no-default",
        action="store_true",
        help="Do not set this account as the default",
    )
    login.set_defaults(func=cmd_login)

    status = sub.add_parser("status", help="Show saved accounts")
    status.add_argument("--check", action="store_true", help="Verify default token against API")
    status.set_defaults(func=cmd_status)

    logout = sub.add_parser("logout", help="Remove saved account")
    logout.add_argument("-u", "--username", default=None, help="Account to remove (default: default account)")
    logout.set_defaults(func=cmd_logout)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
