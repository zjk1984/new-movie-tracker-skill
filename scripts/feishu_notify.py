#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Send scan / download summaries to Feishu (Lark) via tenant app."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

SKILL_DIR = Path(__file__).resolve().parent.parent
FEISHU_API = "https://open.feishu.cn/open-apis"
TOKEN_CACHE: dict[str, Any] = {"token": "", "expires_at": 0.0}


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


def resolve_app_credentials() -> tuple[str, str]:
    app_id = (os.environ.get("FEISHU_APP_ID") or "").strip()
    app_secret = (os.environ.get("FEISHU_APP_SECRET") or "").strip()
    if not app_id or not app_secret:
        raise RuntimeError(
            "missing FEISHU_APP_ID / FEISHU_APP_SECRET in .env.local or environment"
        )
    return app_id, app_secret


def resolve_receive_target() -> tuple[str, str]:
    receive_id = (os.environ.get("FEISHU_RECEIVE_ID") or "").strip()
    if not receive_id:
        raise RuntimeError(
            "missing FEISHU_RECEIVE_ID (chat_id / open_id / user_id of target chat)"
        )
    receive_id_type = (os.environ.get("FEISHU_RECEIVE_ID_TYPE") or "chat_id").strip()
    return receive_id, receive_id_type


def get_tenant_access_token(*, force: bool = False) -> str:
    now = time.time()
    cached = TOKEN_CACHE.get("token") or ""
    if cached and not force and now < float(TOKEN_CACHE.get("expires_at") or 0):
        return cached

    app_id, app_secret = resolve_app_credentials()
    resp = requests.post(
        f"{FEISHU_API}/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"feishu token error: {data.get('msg') or data}")

    token = data["tenant_access_token"]
    expire = int(data.get("expire") or 7200)
    TOKEN_CACHE["token"] = token
    TOKEN_CACHE["expires_at"] = now + max(expire - 120, 60)
    return token


def send_text(
    text: str,
    *,
    receive_id: str | None = None,
    receive_id_type: str | None = None,
) -> dict[str, Any]:
    rid, rid_type = resolve_receive_target()
    if receive_id:
        rid = receive_id
    if receive_id_type:
        rid_type = receive_id_type

    token = get_tenant_access_token()
    body = {
        "receive_id": rid,
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False),
    }
    resp = requests.post(
        f"{FEISHU_API}/im/v1/messages",
        params={"receive_id_type": rid_type},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json=body,
        timeout=20,
    )
    data = resp.json()
    if resp.status_code >= 400 or data.get("code") not in (0, None):
        raise RuntimeError(f"feishu send failed: HTTP {resp.status_code} {data}")
    return data


def format_scan_summary(
    result_path: Path,
    *,
    pikpak_ok: int | None = None,
    pikpak_total: int | None = None,
    extra_lines: list[str] | None = None,
) -> str:
    sys.path.insert(0, str(SKILL_DIR / "scripts"))
    from content_filter import is_downloadable

    data = json.loads(result_path.read_text(encoding="utf-8"))
    matched = data.get("matched") or []
    downloadable = [m for m in matched if is_downloadable(m)]
    with_mag = [m for m in downloadable if m.get("selected_magnet") or m.get("magnets")]
    with_ed2k = [m for m in downloadable if m.get("selected_ed2k") or m.get("ed2k")]
    with_dl = [m for m in downloadable if m.get("selected_download") or m.get("selected_magnet")]

    lines = [
        "📺 论坛扫描报告",
        f"时间: {data.get('scan_time', '')[:19]}",
        f"匹配: {len(matched)} | 可下载: {len(downloadable)} | 有磁力: {len(with_mag)} | 有ed2k: {len(with_ed2k)}",
    ]
    if pikpak_ok is not None and pikpak_total is not None:
        lines.append(f"PikPak 提交: {pikpak_ok}/{pikpak_total}")

    javdb = data.get("javdb_summary") or {}
    if javdb:
        lines.append(
            "JavDB: "
            f"查询 {javdb.get('queried', 0)} | "
            f"有磁力 {javdb.get('with_magnet', 0)} | "
            f"错误 {javdb.get('errors', 0)}"
        )

    if extra_lines:
        lines.extend(extra_lines)

    lines.append("")
    lines.append("── 新增可下载 ──")
    shown = 0
    for item in with_dl[:12]:
        title = (item.get("title") or "")[:60]
        num = item.get("av_number") or ""
        region = item.get("content_region") or ""
        subtype = item.get("domestic_subtype") or ""
        tag = subtype or region or "?"
        src = item.get("magnet_source") or item.get("download_source") or ""
        prefix = f"{num} " if num else ""
        lines.append(f"• [{tag}] {prefix}{title}")
        if src:
            lines.append(f"  ↳ {src}")
        shown += 1
    if len(with_dl) > shown:
        lines.append(f"... 另有 {len(with_dl) - shown} 条")

    if not with_dl:
        lines.append("(无可下载项)")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3990] + "\n...(截断)"
    return text


def notify_scan_result(
    result_path: Path,
    *,
    pikpak_ok: int | None = None,
    pikpak_total: int | None = None,
    extra_lines: list[str] | None = None,
) -> dict[str, Any]:
    text = format_scan_summary(
        result_path,
        pikpak_ok=pikpak_ok,
        pikpak_total=pikpak_total,
        extra_lines=extra_lines,
    )
    return send_text(text)


def is_configured() -> bool:
    try:
        resolve_app_credentials()
        resolve_receive_target()
        return True
    except RuntimeError:
        return False


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    load_env_local()
    parser = argparse.ArgumentParser(description="Send Feishu notifications for scan results")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ping = sub.add_parser("ping", help="Verify app credentials (tenant token only)")
    ping.set_defaults(func="ping")

    send = sub.add_parser("send", help="Send a plain text message")
    send.add_argument("text", help="Message body")
    send.set_defaults(func="send")

    summary = sub.add_parser("summary", help="Send summary from last_result.json")
    summary.add_argument(
        "--input",
        default=str(SKILL_DIR / "last_result.json"),
        help="Path to last_result.json",
    )
    summary.add_argument("--pikpak-ok", type=int, default=None)
    summary.add_argument("--pikpak-total", type=int, default=None)
    summary.set_defaults(func="summary")

    args = parser.parse_args()

    try:
        if args.func == "ping":
            token = get_tenant_access_token(force=True)
            print(f"[ok] tenant_access_token acquired ({token[:12]}...)")
            if os.environ.get("FEISHU_RECEIVE_ID"):
                send_text("飞书通知测试 OK")
                print("[ok] test message sent")
            else:
                print("[info] FEISHU_RECEIVE_ID not set — token OK, skipping send")
            return 0

        if args.func == "send":
            send_text(args.text)
            print("[ok] message sent")
            return 0

        if args.func == "summary":
            notify_scan_result(
                Path(args.input),
                pikpak_ok=args.pikpak_ok,
                pikpak_total=args.pikpak_total,
            )
            print("[ok] summary sent")
            return 0
    except Exception as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
